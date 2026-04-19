---
description: Analyze a prompt for token inefficiency and get improvement suggestions
argument-hint: "<your prompt text>"
allowed-tools: [Bash]
---

Analyze the following prompt for token efficiency issues using the prompt-efficiency-analyzer plugin.

Run this command and report the results to the user:

```bash
python3 -c "import json,sys; print(json.dumps({'session_id':'manual','prompt':sys.argv[1]}))" "$ARGUMENTS" \
  | python3 ${CLAUDE_PLUGIN_ROOT}/hooks/analyze_efficiency.py
```

If the script returns a JSON object with a `systemMessage` key, display the warning message clearly to the user.

If there are no high-severity signals (empty output), tell the user: "This prompt looks efficient -- no high-severity issues detected."

Also describe any medium or low signals if the user wants more detail — you can re-run the analysis by calling the script directly and parsing its full output.
