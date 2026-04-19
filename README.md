# prompt-efficiency-analyzer

A Claude Code plugin that intercepts user prompts and warns when they are likely to waste tokens — before they're sent to Claude.

## What It Does

Every prompt you submit is analyzed by Claude Haiku for six inefficiency signals:

| Signal | Description |
|--------|-------------|
| `vague_scope` | No concrete deliverable ("make it better") |
| `tool_overuse_trigger` | Phrasing that implies broad file scanning |
| `missing_context` | Missing file path, error, or language info |
| `round_trip_bait` | Decision question without needed context |
| `redundant_instructions` | Same constraint repeated multiple times |
| `padding` | Filler preamble with no semantic value |

**High-severity signals** surface as a warning injected into Claude's context before it responds. Low/medium signals are logged silently for later review.

## Commands

### `/analyze-prompt <your prompt>`

Analyze any prompt text on demand and get detailed efficiency feedback with suggested fixes.

## Skills

The `prompt-efficiency` skill teaches Claude to explain and improve prompt efficiency when asked.

## Logs

All analysis results are saved to `~/.claude/efficiency-logs/<session_id>.jsonl` (permissions: 600).

## Installation

```bash
claude plugin install github:RBDurgin/prompt-efficiency-analyzer
```

## How It Works

The `UserPromptSubmit` hook fires before Claude processes your message. A Python script sends your prompt text (as data to analyze, not as a command) to Claude Haiku via `claude -p`. A sentinel environment variable (`CLAUDE_EFFICIENCY_ANALYZING`) prevents the analysis call from recursively triggering the hook. The whole process completes within 30 seconds; if it times out, the hook exits silently and your prompt proceeds normally.
