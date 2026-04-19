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

## Examples

Each example shows a prompt that triggers the signal and a revised version that avoids it.

### `vague_scope`
> **Poor:** `look at my code and make it better`  
> **Better:** `Refactor src/auth/login.ts to reduce cyclomatic complexity — keep the public API unchanged`

### `tool_overuse_trigger`
> **Poor:** `search everywhere for any TODO comments and fix them all`  
> **Better:** `List all TODO comments in src/api/ and fix the three oldest ones`

### `missing_context`
> **Poor:** `I'm getting a type error, can you fix it?`  
> **Better:** `Fix the TypeScript error on line 42 of src/models/user.ts: "Property 'id' does not exist on type 'UserInput'"`

### `round_trip_bait`
> **Poor:** `Should I use PostgreSQL or SQLite for this project?`  
> **Better:** `We have ~10k daily users, need full-text search, and are deploying to Railway — recommend PostgreSQL or SQLite and explain why`

### `redundant_instructions`
> **Poor:** `Write tests. Make sure the tests cover edge cases. Don't forget to test edge cases.`  
> **Better:** `Write unit tests for src/utils/parser.ts covering edge cases: empty input, max-length strings, and invalid UTF-8`

### `padding`
> **Poor:** `I would really appreciate it if you could please carefully and thoroughly review my PR`  
> **Better:** `Review my PR for correctness and flag any bugs or missing error handling`

---

### Full example: poor vs. good

**Poor prompt** (triggers `padding` + `vague_scope` + `missing_context` — overall: poor, token_risk: high):
> `Hey, I was just wondering if you could maybe take a look at my code and see if there's anything wrong with it or anything that could be improved`

**Good prompt** (overall: good, token_risk: low):
> `Review src/payments/stripe.ts for error handling gaps — specifically around webhook signature validation and failed charge retries`

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

The `UserPromptSubmit` hook fires before Claude processes your message. The harness passes a JSON object on stdin with `session_id` (the current session identifier) and `prompt` (the full user message text). The Python script sends your prompt text (as data to analyze, not as a command) to Claude Haiku via `claude -p`. A sentinel environment variable (`CLAUDE_EFFICIENCY_ANALYZING`) prevents the analysis call from recursively triggering the hook. The whole process completes within 25 seconds; if it times out or fails, the hook exits silently with code 0 and your prompt proceeds normally. High-severity results are returned as a JSON `systemMessage` on stdout; all results (including low/medium) are appended to the session log file.

## Troubleshooting

**Hook doesn't fire / no warnings appear**
- Verify the plugin is installed: `claude plugin list`
- Confirm `claude -p` works: `echo "hello" | claude -p "say hi" --model claude-haiku-4-5-20251001 --output-format text`
- Check logs exist: `ls ~/.claude/efficiency-logs/`

**`claude -p` not found**
- The hook requires Claude Code CLI on `$PATH`. Run `which claude` to confirm.

**Warnings fire on every prompt**
- Check if `CLAUDE_EFFICIENCY_ANALYZING` is stuck set in your shell environment: `echo $CLAUDE_EFFICIENCY_ANALYZING`. If non-empty, `unset CLAUDE_EFFICIENCY_ANALYZING`.

**Log files not created**
- Check permissions on `~/.claude/`: `ls -la ~/.claude/`
- The hook creates `~/.claude/efficiency-logs/` automatically with mode 700.
