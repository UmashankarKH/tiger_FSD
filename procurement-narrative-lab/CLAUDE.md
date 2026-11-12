# Procurement Narrative Lab

Python 3.12+ and pytest. Model output lives in `data/`. Narratives are written in `output/`.

## Commands

- `python3 -m pytest` runs the checker tests.
- `python3 src/check_summary.py output/exec_summary.md --table data/category_model_output.csv` checks a draft.

## Conventions

- Every number in an executive summary must appear in `data/category_model_output.csv`, or be derived from it in the text with the derivation stated.
- Use exactly three paragraphs for the executive summary: finding, drivers, action.
- State the confidence level for every model-based claim. Use the phrasing rules in `prompts/confidence_language.md`.
- Never describe a SHAP value as a causal effect. Say it shows contribution to the prediction.
- Write for the audience in `prompts/personas.md`. Name the audience at the top of the draft.
