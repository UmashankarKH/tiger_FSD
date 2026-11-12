"""Deterministic checks for a procurement executive summary.

Checks:
1. Exactly three paragraphs (headings and an 'Audience:' line are ignored).
2. Every number traces to the model output table, or its sentence says it was derived or calculated.
3. The text names the model's holdout metrics and uses hedged language.
4. SHAP values are never described as causes.

No LLM is called. Exit code 0 when all checks pass, 1 otherwise.
"""

import argparse
import re
import sys
from pathlib import Path

NUMBER_RE = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")
HEDGES = ("points to", "consistently ranks", "limited", "predicted", "moderate", "suggests")
METRIC_WORDS = ("auc", "recall", "precision")
CAUSAL_PHRASES = ("causes", "caused by", "causal effect", "drives overruns because", "leads to overruns")
DERIVATION_WORDS = ("derived", "calculated", "computed")
TOLERANCE = 1e-6


def table_numbers(csv_text: str) -> set[float]:
    """All numbers in the table, plus percent forms of values between 0 and 1."""
    values: set[float] = set()
    for token in NUMBER_RE.findall(csv_text):
        number = float(token)
        values.add(number)
        if 0 < number < 1:
            values.add(round(number * 100, 6))
    return values


def split_paragraphs(markdown: str) -> list[str]:
    """Non-empty blocks separated by blank lines, skipping headings and the audience line."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", markdown) if b.strip()]
    kept = []
    for block in blocks:
        if block.startswith("#") or block.lower().startswith("audience"):
            continue
        kept.append(" ".join(block.split()))
    return kept


def sentences(paragraph: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", paragraph) if s]


def untraced_numbers(paragraphs: list[str], table: set[float]) -> list[str]:
    problems = []
    for paragraph in paragraphs:
        for sentence in sentences(paragraph):
            if any(word in sentence.lower() for word in DERIVATION_WORDS):
                continue
            for token in NUMBER_RE.findall(sentence):
                number = float(token)
                if not any(abs(number - v) < TOLERANCE for v in table):
                    problems.append(f"number {token} is not in the table: {sentence[:80]}")
    return problems


def check_summary(markdown: str, csv_text: str) -> list[str]:
    problems: list[str] = []
    paragraphs = split_paragraphs(markdown)

    if len(paragraphs) != 3:
        problems.append(f"expected 3 paragraphs, found {len(paragraphs)}")

    problems += untraced_numbers(paragraphs, table_numbers(csv_text))

    lowered = " ".join(paragraphs).lower()
    if not any(word in lowered for word in METRIC_WORDS):
        problems.append("no holdout metric (AUC, recall or precision) is named")
    if not any(hedge in lowered for hedge in HEDGES):
        problems.append("no hedged or confidence language found")

    if "shap" in lowered and any(phrase in lowered for phrase in CAUSAL_PHRASES):
        problems.append("SHAP value described as a cause")

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("summary", type=Path, help="Markdown draft of the executive summary")
    parser.add_argument("--table", type=Path, required=True, help="Model output CSV")
    args = parser.parse_args()

    problems = check_summary(args.summary.read_text(encoding="utf-8"), args.table.read_text(encoding="utf-8"))
    if not problems:
        print("PASS: all checks passed")
        return 0
    for problem in problems:
        print(f"FAIL: {problem}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
