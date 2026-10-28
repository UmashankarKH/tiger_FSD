#!/usr/bin/env python3
"""Generate a pytest suite with Claude, run it, and let Claude repair it once.

    python tools/gen_tests.py src/procurement_fixed.py --out tests/generated/test_generated_procurement.py

The loop is the point: generated tests are a draft until they have been RUN.
If they fail, the failures go back to the model with the rule that it must not
weaken an assertion just to get green. Real bugs are flagged with `# BUG:`.

Add CPG_DRY_RUN=1 to use the canned test file instead of calling the API.
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

import llm

ROOT = Path(__file__).resolve().parent.parent
SYSTEM = (ROOT / "prompts" / "test_generation.md").read_text()


def build_request(module_path, conftest_path):
    return (
        f"## Module under test: {module_path.name}\n```python\n{module_path.read_text()}\n```\n\n"
        f"## conftest.py\n```python\n{conftest_path.read_text()}\n```"
    )


def run_pytest(test_file, module_name):
    env = {**os.environ, "CPG_TARGET": module_name}
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-q", "-p", "no:cacheprovider", "--no-header"],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    return result.returncode == 0, result.stdout + result.stderr


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("module", help="module to write tests for, e.g. src/procurement_fixed.py")
    parser.add_argument("--out", required=True, help="where to write the generated test file")
    parser.add_argument("--repair-rounds", type=int, default=1)
    args = parser.parse_args(argv)

    module_path = Path(args.module).resolve()
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    if llm.is_dry_run():
        print("[dry run] using the canned test file from tools/fixtures/; no API calls are made\n")

    request = build_request(module_path, ROOT / "tests" / "conftest.py")
    code = llm.extract_code(llm.complete("tester", SYSTEM, request, max_tokens=8000))
    passed = False
    for attempt in range(args.repair_rounds + 1):
        out.write_text(code)
        passed, output = run_pytest(out, module_path.stem)
        print(f"Attempt {attempt + 1}: {'all tests pass' if passed else 'failures'}")
        if passed or attempt == args.repair_rounds:
            break
        repair = (
            f"{request}\n\n## Your test file\n```python\n{code}\n```\n\n## pytest output\n```\n{output[-6000:]}\n```\n\n"
            "Fix the test file. Change a test only if the TEST is wrong. If the failure reveals a real bug in the "
            "module, keep the correct assertion and mark it with `# BUG:`. Never weaken an assertion just to pass."
        )
        code = llm.extract_code(llm.complete("tester", SYSTEM, repair, max_tokens=8000))

    print("\n" + "\n".join(output.strip().splitlines()[-12:]))
    bug_notes = [line.strip() for line in code.splitlines() if "# BUG:" in line]
    if bug_notes:
        print("\nThe model flagged possible bugs in the module (review these by hand):")
        print("\n".join(f"  {note}" for note in bug_notes))
    print(f"\nWrote {out.relative_to(ROOT) if out.is_relative_to(ROOT) else out}")
    summary = llm.usage_summary()
    if summary:
        print("\nUsage:\n" + summary)
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
