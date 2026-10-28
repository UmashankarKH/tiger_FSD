# CPG Review Lab

Python 3.12+ and pytest. Two modules expose the same public API:

- `src/procurement_legacy.py`: the lab exhibit. Deliberately bloated and insecure. **Never edit it.** Copy it to `src/procurement_mine.py` and work there.
- `src/procurement_fixed.py`: the answer key.

## Commands

- `python3 -m pytest` runs everything against `procurement_fixed`.
- `CPG_TARGET=procurement_mine python3 -m pytest tests/test_behavior.py tests/test_security.py` runs the shared tests against your copy.
- `python3 tools/bloat_check.py <file> --also-scan tests` is the no-LLM bloat check.
- `bandit -r <file>` is the security linter.
- `CPG_DRY_RUN=1 python3 tools/judge_pipeline.py review <file> --no-fail` runs the LLM judge on canned answers (drop `CPG_DRY_RUN` and set `ANTHROPIC_API_KEY` for real calls).

## Conventions

- Plain functions over classes. No abstract base class or factory without at least two real implementations.
- SQL is parameterized. Never build SQL, shell commands or file paths from raw input.
- Raise specific exceptions. Never write `except Exception` unless it re-raises.
- No checks for conditions that cannot occur (a None that was just built, a negative length, a clamp on a ratio).
- Every public function has a test that uses the `proc` fixture from `tests/conftest.py`.

## Review rule

Code written by the `lean-coder` subagent must be reviewed by the `bloat-judge` subagent before it is shown to me. Show me the judge's findings table and what changed because of it.
