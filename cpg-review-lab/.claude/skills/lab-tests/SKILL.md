---
name: lab-tests
description: Generate a pytest suite for a module, run it, and repair it without weakening assertions. Use when asked to write tests for a file in the CPG review lab.
argument-hint: "[module file]"
allowed-tools: Read Write Edit Grep Glob Bash(python3 -m pytest *)
---

Write tests for `$ARGUMENTS`.

1. Read `prompts/test_generation.md` and follow its rules, then read the module and `tests/conftest.py`.
2. Write the suite to `tests/generated/test_<module>.py` (create the folder if needed). Use the `proc` fixture and `CPG_TARGET=<module name without .py>` when running.
3. Run it with `python3 -m pytest tests/generated -q`. If tests fail, decide for each one whether the TEST is wrong or the MODULE is wrong. Fix a wrong test. For a wrong module, keep the correct assertion, mark it `# BUG:` with a one-line reason, and tell me.
4. Never weaken an assertion just to get green, and never edit the module under test.
5. Finish with the pass/fail count and a list of any `# BUG:` notes.
