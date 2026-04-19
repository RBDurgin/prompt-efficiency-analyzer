#!/usr/bin/env python3
"""
UserPromptSubmit hook for prompt-efficiency-analyzer plugin.
Analyzes each user prompt for token inefficiency using Claude Haiku.
Emits a systemMessage warning only when at least one signal is high severity.
Low/medium signals are logged to ~/.claude/efficiency-logs/<session_id>.jsonl.
Non-blocking: always exits 0.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from typing import Optional

from utils import strip_fence


LOG_DIR = os.path.expanduser("~/.claude/efficiency-logs")
_SENTINEL_ENV = "CLAUDE_EFFICIENCY_ANALYZING"

_ANALYSIS_SYSTEM_PROMPT = """\
You are a prompt efficiency evaluator. Your job is to analyze a user prompt submitted to an AI coding assistant and identify patterns that will waste tokens.

Return ONLY a valid JSON object with no markdown fences, no explanation — just the raw JSON:
{
  "signals": [
    {
      "type": "<one of: vague_scope|tool_overuse_trigger|missing_context|round_trip_bait|redundant_instructions|padding>",
      "severity": "<low|medium|high>",
      "explanation": "<one sentence describing the specific issue in this prompt>",
      "suggested_fix": "<one sentence concrete suggestion to improve this prompt>"
    }
  ],
  "overall_efficiency": "<good|fair|poor>",
  "token_risk": "<low|medium|high>"
}

Signal definitions:
- vague_scope: The request has no concrete deliverable (e.g. "make it better", "look at my code", "fix the issues")
- tool_overuse_trigger: Phrasing that implies broad file scanning, searching everywhere, or running many tools unnecessarily
- missing_context: A file path, error message, or language/framework is clearly needed but absent
- round_trip_bait: A decision question that cannot be answered without more info the user should have provided
- redundant_instructions: The same constraint or instruction is repeated more than once
- padding: Filler preamble that adds tokens without adding meaning (e.g. "I want you to please carefully...")

Only include signals that are clearly present. Return an empty signals array if the prompt is efficient. A high severity signal means it will very likely cause wasted tokens or extra round-trips.\
"""


def analyze_efficiency(prompt_text: str) -> Optional[dict]:
    """Call claude -p to analyze prompt efficiency. Returns parsed dict or None on failure."""
    analysis_prompt = f"{_ANALYSIS_SYSTEM_PROMPT}\n\nUser prompt to analyze:\n{prompt_text}"

    env = {**os.environ, _SENTINEL_ENV: "1"}
    try:
        result = subprocess.run(
            [
                "claude",
                "-p",
                analysis_prompt,
                "--model",
                "claude-haiku-4-5-20251001",
                "--output-format",
                "text",
            ],
            capture_output=True,
            text=True,
            timeout=25,
            env=env,
        )
        if result.returncode != 0:
            return None

        text = strip_fence(result.stdout.strip())
        return json.loads(text)
    except Exception:
        return None


def build_warning_message(analysis: dict) -> Optional[str]:
    """Build a systemMessage string if any signal is high severity, else None."""
    high_signals = [s for s in analysis.get("signals", []) if s.get("severity") == "high"]
    if not high_signals:
        return None

    lines = [
        f"⚠️ Prompt Efficiency Warning (token_risk: {analysis.get('token_risk', 'unknown')}):",
    ]
    for sig in high_signals:
        lines.append(f"• [{sig['type']}] {sig['explanation']}")
        if sig.get("suggested_fix"):
            lines.append(f"  → {sig['suggested_fix']}")

    lines.append(
        "\nConsider revising the prompt before proceeding to reduce unnecessary token usage."
    )
    return "\n".join(lines)


def main():
    # Prevent infinite recursion: this hook calls `claude -p`, which itself fires
    # UserPromptSubmit hooks. Bail immediately if we're already inside an analysis.
    if os.environ.get(_SENTINEL_ENV):
        sys.exit(0)

    try:
        input_data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    raw_session_id = input_data.get("session_id", "unknown")
    # Sanitize session_id to prevent path traversal when constructing log path
    session_id = re.sub(r"[^a-zA-Z0-9_-]", "_", os.path.basename(raw_session_id)) or "unknown"
    prompt_text = input_data.get("prompt", "")

    if not prompt_text.strip():
        sys.exit(0)

    analysis = analyze_efficiency(prompt_text)

    # Log every result (low/medium too) for later review
    os.makedirs(LOG_DIR, mode=0o700, exist_ok=True)
    log_path = os.path.join(LOG_DIR, f"{session_id}.jsonl")
    log_entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_id": session_id,
        "prompt_length": len(prompt_text),
        "prompt_preview": prompt_text[:200],
        "analysis": analysis,
    }
    try:
        with open(log_path, "a", opener=lambda p, f: os.open(p, f, 0o600)) as fh:
            fh.write(json.dumps(log_entry) + "\n")
    except IOError:
        pass

    # Only surface a warning to Claude when at least one signal is high severity
    if analysis:
        warning = build_warning_message(analysis)
        if warning:
            print(json.dumps({"systemMessage": warning}))

    sys.exit(0)


if __name__ == "__main__":
    main()
