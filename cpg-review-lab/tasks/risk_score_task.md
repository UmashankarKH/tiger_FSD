# Task: on-time delivery risk bucket

Write one function:

    supplier_risk(deliveries, today)

- `deliveries` is a list of dicts with ISO date strings `promised` and `delivered`. `delivered` is `None` when the order has not arrived yet.
- `today` is an ISO date string (`YYYY-MM-DD`).
- Only count deliveries whose `delivered` date falls in the 90 days up to and including `today`.
- A delivery is late if `delivered` is after `promised`.
- Return a dict: `{"late_pct": float rounded to 1 decimal, "bucket": "Low" | "Medium" | "High" | "Unknown", "sample_size": int}`.
- Buckets: `late_pct` below 10 is Low, below 25 is Medium, otherwise High.
- If no deliveries fall in the window: `late_pct` is `None`, bucket is `"Unknown"`, `sample_size` is 0.
- Raise `ValueError` if any date string is not valid `YYYY-MM-DD`.
