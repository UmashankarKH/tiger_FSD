---
name: lab-judge
description: Run the independent bloat-judge subagent on a file and report its verdict. Use after code has been written or changed, before showing it to the user.
argument-hint: "[file]"
allowed-tools: Read Grep Glob
---

Use the `bloat-judge` subagent to review `$ARGUMENTS`. Pass it the file path and nothing else: do not summarize your own opinion of the code, because the judge must form its own view.

When it returns, show its findings table and verdict unchanged. Then, in two or three lines, say which findings you would fix first and why. Do not edit any files until I say so.
