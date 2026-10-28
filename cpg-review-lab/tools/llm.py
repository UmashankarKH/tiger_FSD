"""Thin wrapper around the Anthropic SDK, plus a dry-run mode for the classroom.

    export ANTHROPIC_API_KEY=...        # real calls
    export CPG_DRY_RUN=1                # canned answers from tools/fixtures/, no key or network needed

Models are chosen per role so cost follows the job: a small fast model writes,
a larger one judges. Override with environment variables.
"""
import os
import re
from collections import defaultdict
from pathlib import Path

DEFAULT_MODELS = {
    "generator": os.environ.get("GENERATOR_MODEL", "claude-haiku-5-5"),
    "judge": os.environ.get("JUDGE_MODEL", "claude-sonnet-5-5"),  # claude-opus-5-5 for high-stakes code
    "reviewer": os.environ.get("JUDGE_MODEL", "claude-sonnet-5-5"),
    "tester": os.environ.get("TESTER_MODEL", "claude-sonnet-5-5"),
}
FIXTURES = Path(__file__).parent / "fixtures"

usage = defaultdict(lambda: {"calls": 0, "input_tokens": 0, "output_tokens": 0})
_dry_run_calls = defaultdict(int)


def is_dry_run():
    return os.environ.get("CPG_DRY_RUN") == "1"


def reset():
    """Forget usage and dry-run call counters (used by tests)."""
    usage.clear()
    _dry_run_calls.clear()


def model_for(role):
    return DEFAULT_MODELS[role]


def complete(role, system, user, max_tokens=4096):
    """Send one request for `role` and return the text of the reply."""
    if is_dry_run():
        return _canned(role)

    import anthropic  # imported lazily so dry-run needs no SDK or key

    client = anthropic.Anthropic()
    response = client.messages.create(
        model=model_for(role),
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    usage[role]["calls"] += 1
    usage[role]["input_tokens"] += response.usage.input_tokens
    usage[role]["output_tokens"] += response.usage.output_tokens
    return "".join(block.text for block in response.content if block.type == "text")


def _canned(role):
    _dry_run_calls[role] += 1
    n = _dry_run_calls[role]
    candidates = sorted(FIXTURES.glob(f"{role}_*.txt"))
    if not candidates:
        raise FileNotFoundError(f"no dry-run fixtures for role {role!r} in {FIXTURES}")
    chosen = FIXTURES / f"{role}_{n}.txt"
    if not chosen.exists():
        chosen = candidates[-1]  # keep returning the last scripted answer
    usage[role]["calls"] += 1
    return chosen.read_text()


def extract_code(text):
    """Return the first fenced code block in `text`, or the text itself if there is none."""
    match = re.search(r"```(?:python)?\s*\n(.*?)```", text, re.DOTALL)
    return (match.group(1) if match else text).strip() + "\n"


def usage_summary():
    lines = []
    for role, u in usage.items():
        lines.append(
            f"  {role:<9} {model_for(role) if not is_dry_run() else '(dry run)':<20} "
            f"{u['calls']} call(s), {u['input_tokens']} in / {u['output_tokens']} out tokens"
        )
    return "\n".join(lines)
