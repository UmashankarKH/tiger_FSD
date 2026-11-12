import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from check_summary import check_summary  # noqa: E402

CSV = (ROOT / "data" / "category_model_output.csv").read_text(encoding="utf-8")

GOOD = """# Audience: Chief Procurement Officer

Raw Materials carries the most predicted overrun risk, with 21.5M USD of spend and a predicted overrun rate of 33%.

The model's top driver is price index vs benchmark at 1.07, with a mean absolute SHAP value of 0.094. SHAP values show contribution to the prediction, not cause. The holdout AUC is 0.81, so the model consistently ranks risky lines well, though its recall at 10% is 0.38.

Action: review contract price clauses for Raw Materials suppliers priced above benchmark first.
"""


def test_good_summary_passes():
    assert check_summary(GOOD, CSV) == []


def test_wrong_paragraph_count_fails():
    two = GOOD.split("\n\n")
    text = "\n\n".join(two[:2])
    problems = check_summary(text, CSV)
    assert any("expected 3 paragraphs" in p for p in problems)


def test_untraced_number_fails():
    text = GOOD.replace("21.5M", "47.9M")
    problems = check_summary(text, CSV)
    assert any("47.9" in p for p in problems)


def test_derived_number_is_allowed():
    text = GOOD.replace(
        "21.5M USD of spend",
        "about 47.9M USD of spend, calculated as 21.5M plus 26.4M",
    )
    problems = check_summary(text, CSV)
    assert not any("47.9" in p for p in problems)


def test_missing_metric_fails():
    text = GOOD.replace("holdout AUC is 0.81", "model is strong").replace("recall at 10% is 0.38", "coverage is fine")
    problems = check_summary(text, CSV)
    assert any("no holdout metric" in p for p in problems)


def test_causal_shap_language_fails():
    text = GOOD.replace("SHAP values show contribution to the prediction, not cause.", "SHAP values show what causes overruns.")
    problems = check_summary(text, CSV)
    assert any("described as a cause" in p for p in problems)
