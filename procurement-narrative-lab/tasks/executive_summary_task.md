# Task: 3-paragraph executive summary for a Procurement category review

Input: `data/category_model_output.csv`. It holds the holdout metrics, the feature SHAP values, and the predicted overrun rate per category.

The model predicts whether a purchase order line will overrun its contract value by more than 5%. Read the metrics before you write anything. Precision and recall are at the 10% cutoff.

## Audiences

Write one summary for the audience you choose. Name the audience on the first line of the draft. The personas are in `prompts/personas.md`.

## Requirements

1. Exactly three paragraphs, in this order:
   - **Finding:** which category carries the most predicted overrun risk, and how much spend sits in it.
   - **Drivers:** the top two or three features by mean absolute SHAP value. Say what each contribution means in plain words. Do not call it a cause.
   - **Action:** one recommended next step, with the category and the feature it targets.
2. Every number must come from the CSV, or be derived from it with the derivation stated in the text.
3. State the confidence of the model. Use the holdout AUC and the recall at 10%. Follow `prompts/confidence_language.md`.
4. Keep it under 300 words.

## Check your draft

```bash
python3 src/check_summary.py output/exec_summary.md --table data/category_model_output.csv
```

The checker reports paragraph count, numbers that do not trace to the table, and whether the uncertainty language is present.
