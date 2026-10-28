# Trainer guide: Code Review, Code Bloat Control, Security & Test Generation

**Format:** 2 hours, theory plus lab. **Audience:** experienced DE / DS / full-stack developers working on CPG procurement and other CPG functions.
**Outcome:** learners can use Claude for rigorous code review, including bloat control through LLM-as-judge, security scanning against the OWASP Top 10, and test generation wired into CI.

---

## The one idea to repeat all session

> AI made writing code cheap. It did not make reading code cheap. So the job has moved from *writing* to *deciding what deserves a human's attention*.

Everything below serves that: structure the review so it finds real problems, let a second model clear the obvious bloat before a human looks, and let tests and CI hold the line.

---

## Before class (15 minutes)

1. `pip install -r requirements.txt`
2. `python3 -m pytest` should end with **82 passed**. Run `CPG_TARGET=procurement_legacy python3 -m pytest tests/test_security.py` and confirm **25 failed, 2 passed**. That contrast is your opening demo.
3. Live API: `export ANTHROPIC_API_KEY=...`, then run `python3 tools/judge_pipeline.py review src/procurement_legacy.py --no-fail` once. No key or bad Wi-Fi? Prefix any `tools/` command with `CPG_DRY_RUN=1` to play canned answers. The flow is identical, only the model's replies are scripted.
4. Check the model names in `tools/llm.py` (`claude-haiku-5-5` generates, `claude-sonnet-5-5` judges) exist in your account. Swap in `claude-opus-5-5` through `JUDGE_MODEL` for the high-stakes demo.
5. Open the repo in Claude Code and type `/` to confirm `lab-review`, `lab-judge` and `lab-tests` appear.
6. Give learners the repo as a zip or a Git clone, and tell them **not to edit `procurement_legacy.py`**. They copy it to `src/procurement_mine.py`.

> Honest status note: the lab code, tests, Bandit and bloat checker were all run end to end. The three LLM scripts were run in dry-run mode only, because no API key was available while building this. Do one real call before class.

---

## Agenda

| Time | Min | Block | Mode |
|---|---|---|---|
| 0:00 | 5 | Opening: why review is the bottleneck | Talk + demo |
| 0:05 | 15 | Structured review prompting | Talk + live prompts |
| 0:20 | 20 | Security pattern recognition (OWASP Top 10:2025) | Talk + live scan |
| 0:40 | 20 | Bloat control and LLM-as-judge | Talk + demo |
| 1:00 | 10 | Test generation and CI | Talk + demo |
| 1:10 | 5 | Break | |
| 1:15 | 40 | Lab (four stages) | Hands-on |
| 1:55 | 5 | Debrief and takeaways | Discussion |

---

## 0:00 Opening (5 min)

**Say:** "Two modules, same API, same behaviour tests. One has 365 lines of code and 25 failing security tests. The other has 225 and none. Same job."

**Demo (90 seconds):**

```bash
python3 tools/bloat_check.py src/procurement_legacy.py --also-scan tests   # 19 findings
python3 tools/bloat_check.py src/procurement_fixed.py  --also-scan tests   # 0 findings
CPG_TARGET=procurement_legacy python3 -m pytest tests/test_behavior.py -q  # 23 passed
CPG_TARGET=procurement_legacy python3 -m pytest tests/test_security.py -q  # 25 failed, 2 passed
```

**Point:** every behaviour test passes on the legacy code. "It works" and "it is safe and lean" are different questions, and only the second one is review's job. The legacy file is a stand-in for what an unsupervised AI draft looks like after four teams have touched it.

---

## 0:05 Structured review prompting (15 min)

### The problem
"Review this code" returns a polite, generic essay. The model has no idea what you care about, in what order, or what a finding should look like.

### The fix: five ingredients
1. **Lenses, one at a time.** Architecture and bloat, correctness, security, readability, performance. Finish one pass before the next so findings don't blur.
2. **Order matters.** Architecture first. If the shape is wrong (four classes for a 20-line job) there is no point polishing line 40.
3. **An output contract.** One table: `#, Pass, Severity, Where, Problem, Fix`. Sorted by severity. Machine-checkable, skimmable.
4. **Evidence and a fix for every finding.** Quote the construct. No fix, no finding.
5. **Permission to say "unsure" or "clean".** This is what stops invented findings.

### Show the contrast live

Weak: `Review this code.`

Strong: open `prompts/structured_review.md` and run it, either with `/lab-review src/procurement_legacy.py` or by pasting it.

Compare the two outputs side by side.

### Context is part of the prompt
`CLAUDE.md` carries the team's conventions (no abstract class without two implementations, parameterized SQL only, no `except Exception`). The reviewer applies *your* rules, not generic ones. Remind them of last week's session: context files are what make Claude work like a teammate.

### Built-in commands to know (as of Claude Code docs, Oct 2026)

| Command | Use it for |
|---|---|
| `/code-review` (alias `/review`) | Review the current diff, a PR number, branch or path for correctness bugs. Flags include `--fix` and `--comment` |
| `/security-review` | Analyze the branch's diff for security vulnerabilities. Needs an `origin` remote |
| `/simplify` | Cleanup pass on changed code: reuse, simplification, efficiency, right level of abstraction. Does not hunt correctness bugs |
| `/usage` (aliases `/cost`, `/stats`) | Session cost and usage |
| `/context` | See what is filling the context window |

Our `lab-*` skills exist so the *team's own rubric* is applied consistently. Built-ins are quick general-purpose passes. Use both.

**Check for understanding (2 min):** ask learners to rewrite `Check my code for problems` into a prompt with the five ingredients. Take two answers aloud.

---

## 0:20 Security pattern recognition (20 min)

### Frame
Security review is pattern recognition: untrusted input flows to a dangerous place without a guard. Teach the *pairs* (input source, dangerous sink), not a list of CVEs.

### OWASP Top 10:2025 (the current list)

| # | Category | In one line | Where it lives in the lab |
|---|---|---|---|
| A01 | Broken Access Control | Users do things they shouldn't | `approve_order` (no role check), `export_report` (path traversal) |
| A02 | Security Misconfiguration | Unsafe defaults, debug on, secrets in code | `DEBUG = True`, hardcoded `SECRET_KEY` |
| A03 | Software Supply Chain Failures | Bad dependencies and build pipeline | Pin and audit dependencies; not planted in this lab |
| A04 | Cryptographic Failures | Weak or missing crypto | MD5 password hashing |
| A05 | Injection | Input becomes code (SQL, shell, path) | `get_supplier_orders`, `export_report` |
| A06 | Insecure Design | Flaws in the design itself | Tokens are `base64(user:role)` by design |
| A07 | Authentication Failures | Broken login or session handling | Hardcoded admin, forgeable token, no expiry |
| A08 | Software or Data Integrity Failures | Trusting unverified data or code | `pickle.loads` on cached data |
| A09 | Security Logging and Alerting Failures | Attacks go unnoticed | No logging of failed logins or denied approvals |
| A10 | Mishandling of Exceptional Conditions | Errors swallowed, leaked, or failing open | Stack traces returned, bad lines silently priced at zero |

Source: OWASP Top 10:2025 as summarized by [Qualys](https://blog.qualys.com/qualys-insights/2026/06/15/what-changed-in-owasp-top-10-2025-and-recommendations-for-each-category) and [The Register](https://www.theregister.com/2025/11/11/new_owasp_top_ten_broken/). A03 and A10 are new in 2025. Older training material uses the 2021 list, so numbers differ (for example Injection was A03 in 2021, and is A05 now). Always name the year.

### Red-flag strings: teach learners to see these on sight

| You see | Think |
|---|---|
| `"... WHERE x = '" + value + "'"` or f-string SQL | SQL injection. Use `?` placeholders |
| `shell=True`, `os.system(` | Command injection. Pass a list, no shell, or avoid the subprocess |
| `os.path.join(BASE, user_input)` | Path traversal. An absolute path *replaces* BASE. Allow-list the name |
| `pickle.loads`, `yaml.load` without safe loader | Code execution on untrusted data. Use JSON |
| `hashlib.md5(` / `sha1(` for passwords | Use scrypt, bcrypt or argon2, with a salt |
| `== "admin"` and a literal password | Backdoor |
| base64 used as a "token" | Not a token. Sign with HMAC and add an expiry |
| `DEBUG = True`, `traceback.format_exc()` in a response | Information leak |
| `except Exception:` followed by a default return | Failure hidden, A10 |
| A function that takes a token but never checks the role | Missing authorization |

### Live demo: three nets, three catches

```bash
bandit -r src/procurement_legacy.py          # 8 issues: 2 high, 2 medium, 4 low
python3 tools/judge_pipeline.py review src/procurement_legacy.py --no-fail
CPG_TARGET=procurement_legacy python3 -m pytest tests/test_security.py -q
```

Bandit is fast and deterministic, but it **sees syntax, not meaning**. It flags `shell=True`, `pickle.loads` and `md5`. It misses the missing role check, the forgeable token, the path traversal and the swallowed bad data. Those need reading comprehension (the LLM) or an executable specification (a test). Fill in the "found by" columns in the answer key at the end of this guide, live, with the class.

**Teach this rule:** *static tool, model, test. Each one catches what the others miss.*

### A caution worth saying out loud
Claude is a strong reviewer, not an oracle. It can miss a flaw or flag a false one. For anything that ships, a human who understands the system signs off, and the tests are the ground truth.

---

## 0:40 Bloat control and LLM-as-judge (20 min)

### What bloat is
Code that costs review time and adds risk but buys nothing. Six kinds, all planted in the lab:

1. **Single-implementation abstractions.** An abstract repository, a factory, and one `sqlite` class.
2. **Dead code.** Four unused helpers and an unused import.
3. **Unneeded singletons and config objects.** `ConfigManager` that nothing configures.
4. **Checks for things that cannot happen.** `if total is None` right after `total = 0.0`. `len(x) < 0`. Clamping a ratio of two counts to 0..100.
5. **Broad `except` that hides failures.** `except Exception: return 0.0`.
6. **Speculative generality.** Flags and options nobody asked for.

Why it matters beyond tidiness: every line needs reading, testing and maintaining. Impossible-case checks also create *false confidence* ("it handles bad data") when it actually hides it.

### Architecture-first review
Before reading a single function, ask three questions of the file list and class list:
- Is the **shape** proportionate to the task?
- Does any abstraction have **fewer than two** real implementations?
- Could a reviewer **delete** this and nothing change?

This takes a minute and removes the most bloat. In the demo, the task asked for one function and Haiku's first draft was four classes and 80 lines.

### The generate-then-judge loop (★ the core pattern)

```
Task ─► Haiku writes ─► Sonnet/Opus judges against rubric ─► approve? ─► human reads only what the judge cleared
              ▲                                                  │ no
              └──────── findings go back ◄──────────────────────┘
```

**Why a different model and a fresh context?** An author tends to rationalize its own output, and a judge that watched the code being written inherits the author's blind spots. A separate reviewer that sees only the code and the rubric is harder to talk into approving. In Claude Code, a subagent starts with a fresh context, which is exactly why `bloat-judge` is a subagent.

**Why a rubric?** The judge needs an approval rule it can apply the same way every time: "approve only if no high findings and no medium-or-higher bloat." See `prompts/judge_rubric.md`.

**Demo:**

```bash
python3 tools/judge_pipeline.py generate tasks/risk_score_task.md --out out/risk_score.py
```

Expected shape of the output (the dry run shows it exactly):

```
Round 1: 80 lines -> judge says revise, bloat 8/10, 7 finding(s)
Round 2: 24 lines -> judge says approve, bloat 1/10, 1 finding(s)
```

Then open the Round 1 findings. The judge caught the swallowed `ValueError` that the task required, an *actual spec violation*, not just style.

**Where it saves time:** the old workflow was "read everything, delete most of it." The new one is "read the judge's table, spot-check, approve what it cleared." The human still owns the decision.

### Run the cheap check first
`tools/bloat_check.py` is deterministic and free: 19 findings on the legacy file. It catches mechanical bloat. The LLM catches semantic bloat (needless layers that *are* used, clamps like `pct > 100`, duplicated logic). Run the free check in CI on every commit and the model on every PR.

### Cost awareness (ties back to Week 2)
- Generation on the small model, judging on the larger one, once per revision. Reading the code once is cheap next to a person reading it.
- Judge a diff or a file at a time, not the whole repo.
- Use Opus only where the cost of a miss is high (auth, payments, data export).
- Check spend in Claude Code with `/usage` (`/cost` is an alias).

### Be honest about the judge's limits
- It can approve something plausible and wrong. **Calibrate it:** run it on code with *known* planted flaws, as in this lab, and count how many it finds. That is your judge's recall.
- Spot-check a sample of approvals.
- Never let the judge be the only gate. Tests and humans stay in the loop.

---

## 1:00 Test generation and CI (10 min)

### Prompting for tests
Give the model the module, `conftest.py` and a rule set (`prompts/test_generation.md`). Ask for categories in order: unit, edge cases, error paths, integration, security. Require a specific assertion in every test.

### The repair loop is the whole trick
`tools/gen_tests.py` writes the tests, **runs** them, and feeds failures back once. Two rules go into the repair prompt:
1. Change a test only if the *test* is wrong.
2. If the failure exposes a real bug in the module, keep the correct assertion and mark it `# BUG:`. Never weaken an assertion just to go green.

> A test that locks in the wrong behaviour is worse than no test. It will defend the bug.

```bash
python3 tools/gen_tests.py src/procurement_fixed.py --out tests/generated/test_generated_procurement.py
```

### Tests as the judge's judge
Our `test_security.py` is an executable specification: 25 of its 27 tests fail on the legacy module and all pass on the fixed one. If a "fix" doesn't turn them green, it isn't a fix. Coverage (100% on the fixed module) is a *floor*; a test only counts if it would fail when the code is wrong.

### CI integration
Open `.github/workflows/review-gate.yml`. Four gates, cheapest first:

1. `pytest` with a coverage floor
2. Bandit at medium severity and above
3. `bloat_check.py` (exit 1 on any finding)
4. LLM judge on files changed in the PR (skipped when no `ANTHROPIC_API_KEY`, which is normal on fork PRs)

`judge_pipeline.py review` exits 1 on a `revise` verdict, so it gates the merge. Alternatives to mention: Claude Code's headless mode (`claude -p`) in CI, and Anthropic's GitHub Action. Check their current docs before promising specifics.

---

## 1:15 Lab (40 min)

**Setup (1 min):** `cp src/procurement_legacy.py src/procurement_mine.py`. Learners fill in the findings sheet (the table at the end, without the "found by" columns).

### Stage 1: Review (10 min)
- Run `bandit -r src/procurement_legacy.py` and `python3 tools/bloat_check.py src/procurement_legacy.py --also-scan tests`.
- In Claude Code: `/lab-review src/procurement_legacy.py`. Then try the built-ins `/security-review` and `/simplify` if there is a branch to diff.
- On the sheet, tick which tool found which issue. Target: all 17.

### Stage 2: Judge (10 min)
- `/lab-judge src/procurement_legacy.py` (runs the `bloat-judge` subagent in a fresh context), or `python3 tools/judge_pipeline.py review src/procurement_legacy.py --json out/review.json`.
- **Score the judge.** How many of the 17 planted issues did it find, and did it invent any? That number is its recall.
- Then run `python3 tools/judge_pipeline.py generate tasks/risk_score_task.md --out out/risk_score.py` and compare Round 1 with the final code.

### Stage 3: Fix (10 min)
- Ask Claude Code to fix **only** the high-severity findings in `src/procurement_mine.py` and delete the bloat, using the `lean-coder` subagent. Then run `/lab-judge src/procurement_mine.py`.
- Check progress with:

```bash
CPG_TARGET=procurement_mine python3 -m pytest tests/test_behavior.py tests/test_security.py -q
python3 tools/bloat_check.py src/procurement_mine.py --also-scan tests
bandit -q -r src/procurement_mine.py
```

Goal: behaviour tests stay green, security tests turn green, bloat findings drop to zero. The fixed module is the answer key if a group gets stuck.

### Stage 4: Tests and CI (10 min)
- `/lab-tests src/procurement_mine.py` (or `python3 tools/gen_tests.py src/procurement_mine.py --out tests/generated/test_generated_mine.py`).
- Run `CPG_TARGET=procurement_mine python3 -m pytest --cov=procurement_mine`. Look at the uncovered lines. Any `# BUG:` notes? Argue about them.
- Read the CI file. What would you add (dependency audit for A03, secret scanning, a required reviewer)?

### Stretch goals
- Write one more planted flaw into your copy and see whether the judge, Bandit and the tests each catch it.
- Switch `JUDGE_MODEL` to `claude-opus-5-5` and compare the findings.
- Add logging for failed logins and denied approvals (A09). The answer key doesn't do this either, so it is a genuine gap to close.

### Common stumbles
| Symptom | Cause and fix |
|---|---|
| `CPG_SECRET_KEY is not set` | Only outside tests. The test fixture sets it. For manual runs, `export CPG_SECRET_KEY=any-long-random-string` |
| Judge returns prose instead of JSON | `parse_verdict` tolerates fences and chatter. If it still fails, rerun; consider the larger model |
| Tests pass on legacy but should fail | You ran the behaviour file. Security tests live in `tests/test_security.py` |
| Generated tests fail on `proc` | The model didn't use the fixture. The repair round fixes this; or restate "use the `proc` fixture" |
| `/lab-*` skills missing | Open Claude Code from the repo root so `.claude/` is picked up |

---

## 1:55 Debrief (5 min)

Takeaways to leave on the screen:

1. **Structure the review.** Lenses, order, output contract, evidence, permission to say "unsure".
2. **Three nets.** A static tool, a model, and tests each catch what the others miss.
3. **Bloat is a defect.** Review architecture first; let a separate judge clear the obvious before a human reads.
4. **Generated tests must be run.** Never weaken an assertion to get green.
5. **Put it in CI**, cheapest gate first, and keep a human on the decision.

**Exit question:** "What is one rule from your own codebase that belongs in `CLAUDE.md` so the judge can enforce it?"

**Check-for-understanding quiz (optional, 5 questions):**
1. Why review architecture before reading functions? *(Cheapest place to remove the most bloat.)*
2. Why should the judge be a different model or a fresh context? *(A judge that watched the generation inherits the author's blind spots.)*
3. Name two flaws Bandit cannot find in the lab. *(Missing role check, forgeable token, path traversal.)*
4. A generated test fails. What are the two legitimate responses? *(Fix the test if the test is wrong; keep the assertion and flag `# BUG:` if the module is wrong.)*
5. Which OWASP 2025 category covers `except Exception: return 0.0`? *(A10 Mishandling of Exceptional Conditions.)*

---

## Answer key: the 17 planted issues

"Bandit" and "bloat_check" columns show what each deterministic tool finds. Everything else needs the model or a test.

### Security (9)

| ID | Issue | Where | OWASP 2025 | Bandit | bloat_check | Test that fails on legacy |
|---|---|---|---|---|---|---|
| S1 | SQL injection via string concatenation | `get_supplier_orders` | A05 | B608 (medium, low confidence) | no | `test_sql_injection_in_supplier_name_returns_nothing` |
| S2 | OS command injection (`shell=True`) | `export_report` | A05 | B602 (high) | no | `test_shell_metacharacters_in_report_name_are_rejected` |
| S3 | Path traversal / absolute path escape | `export_report` | A01 | no | no | `test_report_name_cannot_escape_export_dir` (5 cases), `test_absolute_path_report_name_writes_nothing_outside_exports` |
| S4 | Unsafe deserialization | `load_cached_report` | A08 | B301 (medium) | no | `test_cache_loader_does_not_execute_pickle_payloads` |
| S5 | Hardcoded admin backdoor | `login`, `ADMIN_PASSWORD` | A07 | B105 flags the literal (low) | no | `test_no_hardcoded_admin_backdoor` |
| S6 | Forgeable, non-expiring token; `SECRET_KEY` never used; secret not read from environment | `_make_token`, `verify_token` | A07, A06 | B105 flags the literal only | no | `test_forged_token_is_rejected`, `test_tokens_expire`, `test_missing_secret_key_fails_closed` |
| S7 | No role check on approval | `approve_order` | A01 | no | no | `test_viewer_cannot_approve_orders`, `test_approve_with_forged_token_is_denied` |
| S8 | Unsalted MD5 password hashes | `_hash_password` | A04 | B324 (high) | no | `test_passwords_are_not_stored_as_plain_md5` |
| S9 | Debug traceback returned to caller; return type flips from list to dict | `get_supplier_orders` handler | A10, A02 | no | flags the broad `except` | `test_orders_lookup_never_returns_error_dicts` |

### Correctness (3)

| ID | Issue | Where | Bandit | bloat_check | Test |
|---|---|---|---|---|---|
| C1 | Bad PO lines silently priced at zero; negative quantity accepted; floats for money | `calculate_po_total` | no | flags the broad `except` | `test_invalid_po_lines_raise_instead_of_being_ignored` (6 cases), `test_failed_order_creation_leaves_no_partial_order` |
| C2 | Approving a non-existent PO reports success | `approve_order` | no | no | `test_approving_unknown_order_fails_loudly` |
| C3 | Connections not closed if an exception occurs (no `try/finally`) | `create_order`, `mark_delivered`, `approve_order`, others | no | no | none; model-only finding |

### Bloat (5)

| ID | Issue | Where | bloat_check |
|---|---|---|---|
| B1 | Abstract repository + factory with one implementation; `find_by_name` never called | `AbstractSupplierRepository` and friends | yes (single-impl-abc, unused-code) |
| B2 | Singleton config object nothing configures | `ConfigManager` | partly (flags unused `set` and `reset`) |
| B3 | Four dead helpers, one unused import | `format_currency_legacy`, `_calc_moving_average`, `_normalize_supplier_name_v2`, `legacy_csv_export`, `json` | yes |
| B4 | Checks for impossible conditions | `calculate_po_total`, `get_supplier_orders`, `supplier_risk_score` | partly (6 of 10; misses `late > total`, `pct < 0`, `pct > 100`, `isinstance(pct, float)`) |
| B5 | Broad `except Exception` handlers | `ConfigManager.get`, `calculate_po_total`, `get_supplier_orders`, `verify_token` | yes (4) |

**Scoreboard from the build run:** Bandit reports 8 issues (2 high, 2 medium, 4 low). It clearly catches 4 of the 9 security items (S1, S2, S4, S8) and flags the hardcoded literals behind 2 more (S5, S6), but it cannot see S3, S7 or S9. `bloat_check` reports 19 findings (with `--also-scan tests`). The shared test suite fails 25 of 27 security tests on legacy and passes all 23 behaviour tests on both modules.

---

## Reference: how the pieces fit

```
src/procurement_legacy.py   exhibit (365 code lines)            src/procurement_fixed.py   answer key (225 code lines)
tests/test_behavior.py      23 behaviour tests, both modules    tests/test_security.py     27 security/correctness tests
tools/bloat_check.py        deterministic bloat finder          tools/judge_pipeline.py    generate/judge loop + review gate
tools/gen_tests.py          generate, run, repair tests         tools/llm.py               model roles + dry-run mode
prompts/                    judge rubric, generator, tests, structured review (single source of truth)
.claude/                    agents (lean-coder: haiku, bloat-judge: sonnet), skills (lab-review, lab-judge, lab-tests)
.github/workflows/          review-gate.yml
```

Docs checked while preparing this kit (Oct 2026): [Claude Code commands](https://code.claude.com/docs/en/commands.md), [skills](https://code.claude.com/docs/en/skills.md), [subagents](https://code.claude.com/docs/en/agent-sdk/subagents.md). Command names and flags change between releases, so run `/help` on your class version before presenting.
