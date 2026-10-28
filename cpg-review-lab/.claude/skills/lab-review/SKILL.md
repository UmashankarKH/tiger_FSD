---
name: lab-review
description: Structured four-pass review (architecture and bloat, correctness, security, readability) of one Python file, using the lab's review prompt. Use for the CPG review lab.
argument-hint: "[file]"
allowed-tools: Read Grep Glob
---

Review `$ARGUMENTS` following the structured review prompt in `prompts/structured_review.md`.

1. Read that prompt, then read the target file in full.
2. Work through the four passes in order and keep findings in the pass where they belong.
3. Output the single findings table and the one-line verdict exactly as the prompt describes.
4. Do not edit any file. If `$ARGUMENTS` is empty, ask which file to review.
