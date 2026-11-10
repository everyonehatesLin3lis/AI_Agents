### Deterministic parts (no LLM)

Source: `evals/results/20261109T201508Z_deterministic.json` (run 2026-11-09T20:15:08+00:00, git commit: no commits yet). 14 samples.

**Security rules** (a finding is a `(resource, rule)` pair):

| Group | TP | FP | FN | Precision | Recall | F1 |
|---|---|---|---|---|---|---|
| clean | 0 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| injection | 13 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| mixed | 2 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| vulnerable | 20 | 0 | 0 | 1.00 | 1.00 | 1.00 |
| all | 35 | 0 | 0 | 1.00 | 1.00 | 1.00 |

Critical false positives on the clean samples: **0**.

**Cost estimator** against 11 hand-calculated totals: mean absolute error $0.00, largest error $0.00, mean absolute percentage error 0.00%.

**Retrieval** (34 queries, one expected document each):

| Setting | Hit rate @1 | Hit rate @2 | Hit rate @4 | MRR |
|---|---|---|---|---|
| with service filter | 0.94 | 0.97 | 0.97 | 0.96 |
| without service filter | 0.94 | 0.97 | 0.97 | 0.96 |

**Speed of the deterministic steps:**

| Step | Measurements | Median (ms) | p95 (ms) |
|---|---|---|---|
| parse | 280 | 4.076 | 9.827 |
| security check | 280 | 0.046 | 0.121 |
| cost estimate | 280 | 0.067 | 0.133 |
| retrieve one query | 20 | 246.388 | 294.727 |

![Median time per deterministic step](docs/img/tool_latency.png)

### Full agent, per model

**Not run yet.** No result file exists for the LLM evaluation, so there are no numbers to show here. Set `OPENROUTER_API_KEY` in `.env`, then run `uv run python -m evals.run` and `uv run python -m evals.report`. This section, the model comparison and the ablation tables are then filled in from the saved run.
