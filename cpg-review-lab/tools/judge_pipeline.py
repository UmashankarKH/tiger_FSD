#!/usr/bin/env python3
"""LLM-as-judge for code: a small model writes, a larger model reviews.

Two modes:

  generate  Haiku writes code for a task spec; Sonnet (or Opus) judges it against
            the rubric; the findings go back to Haiku; repeat until approved.

      python tools/judge_pipeline.py generate tasks/risk_score_task.md --out out/risk_score.py

  review    Judge an existing file once. Use it on a legacy module or a PR diff.
            Exits 1 when the verdict is "revise", so it can gate CI.

      python tools/judge_pipeline.py review src/procurement_legacy.py --json out/review.json

Add CPG_DRY_RUN=1 to run the whole flow on canned answers (no API key needed).
"""
import argparse
import json
import sys
from pathlib import Path

import llm

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}
REQUIRED_KEYS = {"verdict", "summary", "bloat_score", "findings"}
MAX_REVIEW_CHARS = 60_000


def load_prompt(name):
    return (PROMPTS / name).read_text()


def parse_verdict(text):
    """Parse the judge's JSON reply, tolerating code fences or stray prose around it."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("judge reply contained no JSON object")
    try:
        verdict = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"judge reply was not valid JSON: {exc}") from exc
    missing = REQUIRED_KEYS - verdict.keys()
    if missing:
        raise ValueError(f"judge reply is missing keys: {sorted(missing)}")
    if verdict["verdict"] not in {"approve", "revise"}:
        raise ValueError(f"unknown verdict {verdict['verdict']!r}")
    verdict["findings"].sort(key=lambda f: SEVERITY_ORDER.get(f.get("severity"), 3))
    return verdict


def judge(task, code, role="judge"):
    user = f"## Task\n{task}\n\n## Code\n```python\n{code}\n```"
    return parse_verdict(llm.complete(role, load_prompt("judge_rubric.md"), user, max_tokens=4096))


def generate(task, previous_code=None, findings=None):
    user = f"## Task\n{task}"
    if previous_code:
        user += (
            f"\n\n## Your previous attempt\n```python\n{previous_code}\n```"
            f"\n\n## Reviewer findings\n{json.dumps(findings, indent=2)}"
            "\n\nRevise the code to resolve every finding. Prefer deleting code to adding code."
        )
    return llm.extract_code(llm.complete("generator", load_prompt("generator_system.md"), user, max_tokens=4096))


def format_report(verdict):
    lines = [f"Verdict: {verdict['verdict'].upper()}   Bloat score: {verdict['bloat_score']}/10", verdict["summary"], ""]
    for i, f in enumerate(verdict["findings"], 1):
        owasp = f" [{f['owasp']}]" if f.get("owasp") else ""
        lines.append(f"{i:>2}. {f['severity'].upper():<6} {f['category']}{owasp}")
        lines.append(f"      evidence: {f['evidence']}")
        lines.append(f"      issue:    {f['issue']}")
        lines.append(f"      fix:      {f['fix']}")
    return "\n".join(lines)


def run_generate(task, max_rounds=3):
    history, code, findings = [], None, None
    for round_no in range(1, max_rounds + 1):
        code = generate(task, previous_code=code, findings=findings)
        verdict = judge(task, code)
        history.append({"round": round_no, "code": code, "verdict": verdict})
        print(
            f"Round {round_no}: {len(code.splitlines())} lines -> judge says {verdict['verdict']}, "
            f"bloat {verdict['bloat_score']}/10, {len(verdict['findings'])} finding(s)"
        )
        if verdict["verdict"] == "approve":
            return code, history, True
        findings = verdict["findings"]
    return code, history, False


def cmd_generate(args):
    task = Path(args.task_file).read_text()
    code, history, approved = run_generate(task, args.max_rounds)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(code)
    print(f"\nWrote {out} ({len(code.splitlines())} lines). Approved by judge: {approved}")
    print("\nFinal judge report:\n" + format_report(history[-1]["verdict"]))
    if args.report:
        Path(args.report).write_text(json.dumps(history, indent=2))
    return 0 if approved else 1


def cmd_review(args):
    source = Path(args.file).read_text()
    if len(source) > MAX_REVIEW_CHARS:
        print(f"{args.file} is {len(source)} characters; review it in smaller pieces.", file=sys.stderr)
        return 2
    task = (
        f"Review the existing file `{args.file}`. There is no separate spec: infer its intent "
        "from the docstrings and names, and flag anything that does not match."
    )
    verdict = judge(task, source, role="reviewer")
    print(format_report(verdict))
    if args.json:
        Path(args.json).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json).write_text(json.dumps(verdict, indent=2))
    return 0 if args.no_fail or verdict["verdict"] == "approve" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="generate code, judge it, loop until approved")
    gen.add_argument("task_file")
    gen.add_argument("--out", required=True)
    gen.add_argument("--max-rounds", type=int, default=3)
    gen.add_argument("--report", help="write the full round-by-round history as JSON")
    gen.set_defaults(func=cmd_generate)

    rev = sub.add_parser("review", help="judge an existing file once")
    rev.add_argument("file")
    rev.add_argument("--json", help="write the verdict as JSON")
    rev.add_argument("--no-fail", action="store_true", help="always exit 0 (classroom use)")
    rev.set_defaults(func=cmd_review)

    args = parser.parse_args(argv)
    if llm.is_dry_run():
        print("[dry run] using canned model answers from tools/fixtures/; no API calls are made\n")
    code = args.func(args)
    summary = llm.usage_summary()
    if summary:
        print("\nUsage:\n" + summary)
    return code


if __name__ == "__main__":
    sys.exit(main())
