# Confidence and uncertainty language

Use these rules for every model-based claim.

1. Give the holdout metric next to the claim. Example: "the model's holdout AUC is 0.81".
2. Translate recall and precision into plain words. Example: "of the overruns that happen, the model flags about 2 in 5 in its top 10% of lines".
3. Say what a SHAP value is: a feature's average contribution to the prediction. Do not say it causes overruns.
4. Use the hedge that matches the evidence:
   - Strong: "the model consistently ranks..." when the feature is in the top three.
   - Moderate: "the model points to..." when it sits lower in the ranking.
   - Weak: "the evidence is limited" when the metric is near 0.5 or the category is small.
5. Never write "will overrun" for a predicted line. Write "is predicted to overrun" or "carries a higher predicted risk of overrunning".
