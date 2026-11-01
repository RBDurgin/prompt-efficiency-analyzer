#!/usr/bin/env python3
"""Shared utilities for prompt-efficiency-analyzer hooks."""

def strip_fence(text: str) -> str:
    """Strip markdown code fences from LLM output."""
    if not text.startswith("```"):
        return text
    lines = text.split("\n")
    body = "\n".join(lines[1:])
    if body.endswith("```"):
        body = body[:-3].rstrip()
    return body
