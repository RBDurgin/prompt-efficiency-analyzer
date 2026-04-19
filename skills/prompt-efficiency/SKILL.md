---
name: prompt-efficiency
description: >
  This skill should be used when the user asks to improve a prompt, make a prompt more efficient,
  reduce token usage, or when the user asks why their prompts cost a lot of tokens. Also triggers
  when the user asks "how do I write better prompts?", "what makes a good prompt?", or
  "why is my prompt inefficient?". Use this skill to evaluate and explain prompt efficiency patterns.
version: 1.0.0
---

# Prompt Efficiency Skill

## The Six Inefficiency Signals

### 1. `vague_scope` — No Concrete Deliverable
**Example:** "look at my code and fix the issues"
**Why it costs:** Forces the model to scan broadly, guess intent, and produce a long exploratory response.
**Fix:** Name the specific file, function, or behavior. "Fix the null pointer in `src/auth.ts:42`."

### 2. `tool_overuse_trigger` — Implicit Broad Scanning
**Example:** "go through all my files and find any bugs"
**Why it costs:** Triggers many Read/Grep tool calls across the whole codebase.
**Fix:** Scope to a directory or file pattern. "Check `src/` for any unhandled promise rejections."

### 3. `missing_context` — Absent Required Information
**Example:** "it's throwing an error, can you fix it?"
**Why it costs:** Forces a clarifying round-trip, doubling the conversation length.
**Fix:** Always include the error message, file path, and relevant code snippet upfront.

### 4. `round_trip_bait` — Unanswerable Decision Questions
**Example:** "should I use REST or GraphQL?"
**Why it costs:** Without codebase context, the model must ask follow-ups or give a generic answer.
**Fix:** Provide constraints. "Given this Express app with 3 endpoints and no existing schema, should I use REST or GraphQL?"

### 5. `redundant_instructions` — Repeated Constraints
**Example:** "be concise. Keep it short. Don't be verbose. Summarize briefly."
**Why it costs:** Extra tokens in the prompt with no additional signal.
**Fix:** State each constraint once, clearly.

### 6. `padding` — Filler Preamble
**Example:** "I would really appreciate it if you could please carefully take a look at..."
**Why it costs:** Inflates input tokens with zero semantic value.
**Fix:** Start directly with the request. "Fix the race condition in `worker.py`."

## Severity Levels

- **High:** Will very likely cause wasted tokens or an extra round-trip. The hook surfaces these as warnings.
- **Medium:** Probably inefficient but depends on context. Logged but not surfaced as warnings.
- **Low:** Minor issue. Worth knowing but unlikely to meaningfully impact cost.

## How to Use This Skill

When a user asks for prompt improvement help:
1. Identify which of the six signals apply to their prompt.
2. Explain the specific issue in their prompt (not the general pattern).
3. Provide a concrete rewrite that eliminates the signal.
4. Mention the expected token savings (qualitative: "avoids 1–2 extra tool calls", "removes clarifying round-trip").

## Efficient Prompt Template

```
[Action verb] [specific target] [expected outcome/constraints]
Context: [relevant file/error/code snippet]
```

Example: "Refactor the `calculateTotal` function in `src/cart.ts` to avoid the O(n²) loop. Keep the existing function signature."
