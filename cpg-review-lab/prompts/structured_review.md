# Structured review prompt (human-in-the-loop, used by /review)

Review the code below in four separate passes. Finish one pass before starting the next, and do not mix findings between passes.

**Pass 1: Architecture and bloat.** Is the structure proportionate to the job? List anything that could be deleted with no change in behaviour: single-implementation abstractions, unused functions and imports, checks that can never fire, broad `except` blocks.

**Pass 2: Correctness.** Walk the edge cases: empty input, boundaries, bad data, inconsistent return types, errors that are swallowed instead of raised.

**Pass 3: Security.** Check against the OWASP Top 10:2025 and name the category for each finding. Look for injection (SQL, shell, path), access control gaps, weak or hardcoded credentials, forgeable tokens, unsafe deserialization, and error handling that leaks internals.

**Pass 4: Readability and performance.** Only what would genuinely slow down a maintainer or break at realistic data sizes.

Output a single table with the columns: `#`, `Pass`, `Severity (high/medium/low)`, `Where (function or line)`, `Problem`, `Fix`. Order rows by severity. Then give a one-line verdict: ship, fix first, or rewrite.

Be specific. If you are not sure something is a problem, say "unsure" and say what you would need to check. Do not invent findings to fill the table.
