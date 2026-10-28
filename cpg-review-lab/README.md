# CPG Review Lab

Hands-on kit for the session **Code Review, Code Bloat Control, Security & Test Generation** (Claude Code training, Week 2).
Read `TRAINER_GUIDE.md` for the full 2-hour plan, talking points and the answer key.

## Quick start

```bash
pip install -r requirements.txt
python3 -m pytest                                                        # 82 passed (fixed module)
CPG_TARGET=procurement_legacy python3 -m pytest tests/test_security.py   # 25 failed, 2 passed (by design)
python3 tools/bloat_check.py src/procurement_legacy.py --also-scan tests # 19 findings
bandit -r src/procurement_legacy.py                                      # 8 issues
```

LLM tools need `ANTHROPIC_API_KEY`. To rehearse without one, prefix any command with `CPG_DRY_RUN=1` to replay canned answers:

```bash
CPG_DRY_RUN=1 python3 tools/judge_pipeline.py generate tasks/risk_score_task.md --out out/risk_score.py
CPG_DRY_RUN=1 python3 tools/judge_pipeline.py review src/procurement_legacy.py --no-fail
CPG_DRY_RUN=1 python3 tools/gen_tests.py src/procurement_fixed.py --out tests/generated/test_generated_procurement.py
```

## What is where

| Path | Purpose |
|---|---|
| `src/procurement_legacy.py` | The exhibit: 17 planted security, correctness and bloat problems. Do not edit |
| `src/procurement_fixed.py` | The answer key, same public API |
| `tests/test_behavior.py` | Behaviour tests that pass on both modules |
| `tests/test_security.py` | Security and correctness tests that fail on legacy and pass on fixed, labelled with OWASP Top 10:2025 |
| `tools/bloat_check.py` | Deterministic bloat finder (no LLM) |
| `tools/judge_pipeline.py` | Haiku generates, Sonnet judges, loop until approved; `review` mode gates CI |
| `tools/gen_tests.py` | Generate pytest tests, run them, repair once |
| `prompts/` | Judge rubric, generator rules, test-generation rules, structured review prompt |
| `.claude/` | `lean-coder` (haiku) and `bloat-judge` (sonnet) subagents; `/lab-review`, `/lab-judge`, `/lab-tests` skills |
| `.github/workflows/review-gate.yml` | CI: tests, Bandit, bloat check, LLM judge |

Run your own fixes against the shared tests: copy the legacy file to `src/procurement_mine.py`, then
`CPG_TARGET=procurement_mine python3 -m pytest tests/test_behavior.py tests/test_security.py`.

All payloads in the security tests are harmless: marker files are written inside pytest's temporary folder only. The legacy module is intentionally vulnerable. Never run it in production.
