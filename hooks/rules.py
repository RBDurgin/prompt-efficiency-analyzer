"""
Rule-based prompt efficiency detectors — no LLM invocation required.
Each detector returns a signal dict or None.
"""

import re
from typing import Optional

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "be", "as", "this", "that",
    "are", "was", "were", "will", "would", "could", "should", "do", "does",
    "did", "not", "my", "your", "i", "me", "we", "us", "you", "he", "she",
    "they", "them", "its", "so", "if", "then", "than", "there", "into",
    "can", "just", "also", "have", "has", "had", "which", "when", "what",
}

_VAGUE_PATTERNS = [
    re.compile(r'\b(fix|improve|make|update|change)\s+(it|this|that|my code|the code|stuff|things)\b', re.I),
    re.compile(r'\b(make it better|clean(?: it)? up|look at my code|fix the issues?|sort it out)\b', re.I),
]

_TOOL_OVERUSE_PATTERN = re.compile(
    r'\b(search|look|check|scan|go through|look through)\b.{0,20}'
    r'\b(everywhere|all files?|entire (?:codebase|repo|project)|whole (?:codebase|repo|project))\b',
    re.I,
)

_ERROR_MENTION = re.compile(r'\b(error|bug|exception|traceback|failing|broken|crash)\b', re.I)
_STACK_TRACE = re.compile(
    r'(^\s{2,}\S|Error:\s|\bat\s+\S+:\d+|File ".+", line \d+)',
    re.MULTILINE,
)
_DEFINITE_REF = re.compile(r'\bthe\s+(file|function|class|method|module|script)\b', re.I)
_NAMED_ENTITY = re.compile(
    r'["`\'][\w./]+["`\']'          # quoted name
    r'|(?<!\w)[\w./]+-?[\w./]*\.\w+'  # bare filename with extension
    r'|\b[A-Z][a-zA-Z0-9_]+(?:\(\))?',  # CamelCase symbol
)

_ROUND_TRIP_PATTERN = re.compile(
    r'\b(which should I|should I use|what\'?s? (?:better|best)|'
    r'which (?:is|would be) (?:better|best)|'
    r'do you (?:think|recommend|prefer)|'
    r'what would you (?:choose|use|pick))\b',
    re.I,
)

_PADDING_LEADING = re.compile(
    r'^(I want you to|Please|Could you please|I would like you to|'
    r'I need you to|As an AI|As a helpful|Kindly)\b',
    re.I,
)
_PADDING_INLINE = re.compile(r'\b(carefully|thoroughly|in detail|step by step)\b', re.I)


def _detect_vague_scope(prompt: str) -> Optional[dict]:
    hits = sum(bool(p.search(prompt)) for p in _VAGUE_PATTERNS)
    if hits == 0:
        return None
    severity = "high" if hits >= 2 else "medium"
    return {
        "type": "vague_scope",
        "severity": severity,
        "explanation": "The request lacks a concrete deliverable; vague phrasing will force clarifying round-trips.",
        "suggested_fix": "Specify exactly what output you expect (e.g. file path, function name, pass/fail criteria).",
    }


def _detect_tool_overuse(prompt: str) -> Optional[dict]:
    if not _TOOL_OVERUSE_PATTERN.search(prompt):
        return None
    return {
        "type": "tool_overuse_trigger",
        "severity": "medium",
        "explanation": "Phrasing implies scanning the entire codebase or all files unnecessarily.",
        "suggested_fix": "Point to specific files or directories so the assistant can target its search.",
    }


def _detect_missing_context(prompt: str) -> Optional[dict]:
    mentions_error = bool(_ERROR_MENTION.search(prompt))
    has_stack_trace = bool(_STACK_TRACE.search(prompt))
    references_file_vaguely = bool(_DEFINITE_REF.search(prompt))
    has_named_entity = bool(_NAMED_ENTITY.search(prompt))

    missing_error_detail = mentions_error and not has_stack_trace
    missing_file_name = references_file_vaguely and not has_named_entity

    count = int(missing_error_detail) + int(missing_file_name)
    if count == 0:
        return None
    severity = "high" if count >= 2 else "medium"
    return {
        "type": "missing_context",
        "severity": severity,
        "explanation": "The prompt references an error or a file/function without providing the actual content needed.",
        "suggested_fix": "Paste the error message/stack trace or name the specific file and function you mean.",
    }


def _detect_round_trip_bait(prompt: str) -> Optional[dict]:
    if not _ROUND_TRIP_PATTERN.search(prompt):
        return None
    return {
        "type": "round_trip_bait",
        "severity": "medium",
        "explanation": "The prompt asks a decision question the user should resolve with known context.",
        "suggested_fix": "Make the decision yourself and ask for implementation help instead.",
    }


def _detect_redundant_instructions(prompt: str) -> Optional[dict]:
    sentences = re.split(r'(?<=[.!?])\s+', prompt.strip())
    if len(sentences) < 2:
        return None

    def tokens(s: str) -> set:
        words = re.findall(r'\b\w+\b', s.lower())
        return {w for w in words if w not in _STOPWORDS and len(w) > 2}

    overlapping_pairs = 0
    for i in range(len(sentences)):
        for j in range(i + 1, len(sentences)):
            a, b = tokens(sentences[i]), tokens(sentences[j])
            if not a or not b:
                continue
            overlap = len(a & b) / min(len(a), len(b))
            if overlap > 0.5:
                overlapping_pairs += 1

    if overlapping_pairs == 0:
        return None
    severity = "medium" if overlapping_pairs >= 2 else "low"
    return {
        "type": "redundant_instructions",
        "severity": severity,
        "explanation": "Multiple sentences repeat the same constraint or instruction.",
        "suggested_fix": "State each requirement once and remove duplicate phrasing.",
    }


def _detect_padding(prompt: str) -> Optional[dict]:
    has_leading = bool(_PADDING_LEADING.match(prompt.strip()))
    inline_hits = len(_PADDING_INLINE.findall(prompt))
    has_inline = inline_hits >= 3

    if not has_leading and not has_inline:
        return None
    severity = "medium" if has_leading else "low"
    return {
        "type": "padding",
        "severity": severity,
        "explanation": "Filler preamble or repeated filler words add tokens without adding meaning.",
        "suggested_fix": "Start with the action verb and skip filler openings like 'I want you to please carefully…'.",
    }


def run_rules(prompt: str) -> dict:
    """Run all detectors and return analysis dict matching the LLM schema."""
    detectors = [
        _detect_vague_scope,
        _detect_tool_overuse,
        _detect_missing_context,
        _detect_round_trip_bait,
        _detect_redundant_instructions,
        _detect_padding,
    ]

    signals = [sig for d in detectors if (sig := d(prompt)) is not None]

    severities = {s["severity"] for s in signals}
    if "high" in severities:
        token_risk = "high"
    elif "medium" in severities:
        token_risk = "medium"
    else:
        token_risk = "low"

    efficiency_map = {"high": "poor", "medium": "fair", "low": "good"}
    overall_efficiency = efficiency_map[token_risk]

    return {
        "signals": signals,
        "overall_efficiency": overall_efficiency,
        "token_risk": token_risk,
    }
