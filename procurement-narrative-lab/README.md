# Procurement Narrative Lab

Hands-on kit for the session **Insight Narrative Generation & Stakeholder Reporting**.

Topics covered:

- Translating model outputs (feature importances, SHAP values, metrics) into executive narratives
- Stakeholder report generation with audience persona calibration
- Recurring commentary templates
- Handling uncertainty and confidence signalling

## Quick start

```bash
pip install -r requirements.txt
python3 -m pytest                                              # checker tests
python3 src/check_summary.py output/exec_summary.md --table data/category_model_output.csv
```

The checker reads a summary written in Markdown and verifies it against the model output table. It does not call an LLM.

## Lab

Convert `data/category_model_output.csv` into a 3-paragraph executive summary for a Procurement category review. The task is in `tasks/executive_summary_task.md`. Write your draft to `output/exec_summary.md`, then run the checker.

## What is where

| Path | Purpose |
|---|---|
| `data/category_model_output.csv` | Model output for the Procurement category review: feature importances, mean absolute SHAP values, direction, and holdout metrics |
| `tasks/executive_summary_task.md` | The lab brief and the three audiences |
| `prompts/personas.md` | Audience persona calibration: CPO, category leads, and Finance |
| `prompts/confidence_language.md` | Phrasing rules for uncertainty and confidence |
| `prompts/narrative_system.md` | System prompt for generating a narrative from model output |
| `src/check_summary.py` | Deterministic checks: paragraph count, numbers traced to the table, and required uncertainty language |
| `tests/test_check_summary.py` | Tests for the checker |
