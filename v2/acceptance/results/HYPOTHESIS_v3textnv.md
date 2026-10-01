# Written BEFORE r_v3textnv results (judge j0032)
Hypothesis (narrow): the validator feedback loop (code finds a problem -> model rewrites) improves answers.
Measured by: v3text (loop ON) vs v3textnv (loop OFF), same text base, same prompt, same model, N=3, same blind judge.
NOT measured: whether Sanity structure is necessary — code could get fields/formulas another way. Stays unproven.
Confound to report: the loop gives the model extra work (rounds) — report rework counts per arm.
53/78 (v3) = 53/78 (v3text) is equal total score in this test, not equality of methods (per-scenario differences exist).
