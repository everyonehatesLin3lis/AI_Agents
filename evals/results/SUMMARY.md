### Deterministic parts (no LLM)

Source: `evals/results/20261110T081110Z_deterministic.json` (run 2026-11-10T08:11:10+00:00, git commit: 532207b8098f278d9c41d73e36b66b9797299b33). 14 samples.

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
| parse | 280 | 3.562 | 7.316 |
| security check | 280 | 0.051 | 0.105 |
| cost estimate | 280 | 0.069 | 0.111 |
| retrieve one query | 20 | 189.213 | 196.157 |

![Median time per deterministic step](docs/img/tool_latency.png)

### Full agent, per model

Source: `evals/results/20261110T095622Z_llm.json` (run 2026-11-10T09:56:21+00:00, git commit: d3ca62f9b13796e96669f58fee1a858a119944d9). Provider: openrouter. 14 samples x 3 runs per configuration. Judge model: openai/gpt-5-mini. Token prices: openrouter live.

**Quality** (configuration `full`):

| Model | Reviews | Security recall | Security precision | Critical on clean | Injection intact | Recs / review | Share with source | Faithfulness | Answer relevancy | LLM fallback rate |
|---|---|---|---|---|---|---|---|---|---|---|
| xiaomi/mimo-v2.6-flash | 42 | 1.00 | 1.00 | 0 | 1.00 | 2.45 | 0.89 | 1.00 | 0.94 | 0.00 |
| deepseek/deepseek-v4-flash | 42 | 1.00 | 1.00 | 0 | 1.00 | 1.19 | 0.92 | 0.99 | 0.90 | 0.02 |
| google/gemini-3.5-flash-lite | 42 | 1.00 | 1.00 | 0 | 1.00 | 0.64 | 1.00 | 1.00 | 0.91 | 0.00 |

**Speed and cost** (configuration `full`):

| Model | Median (s) | p95 (s) | Deterministic steps (s) | LLM steps (s) | LLM calls | Input tokens | Output tokens | USD / review |
|---|---|---|---|---|---|---|---|---|
| xiaomi/mimo-v2.6-flash | 28.55 | 74.87 | 0.66 | 27.78 | 2.90 | 3544 | 1260 | 0.00085 |
| deepseek/deepseek-v4-flash | 11.66 | 40.20 | 0.37 | 10.96 | 2.67 | 2999 | 1719 | 0.00059 |
| google/gemini-3.5-flash-lite | 3.03 | 5.96 | 0.26 | 2.77 | 2.79 | 3139 | 241 | 0.00154 |

![Latency, cost and faithfulness per model](docs/img/models.png)

**Median seconds per graph node:**

| Model | cost_estimate | grade_docs | parse | plan_research | retrieve | rewrite_query | save_feedback | security_check | write_report |
|---|---|---|---|---|---|---|---|---|---|
| xiaomi/mimo-v2.6-flash | 0.00 | 5.25 | 0.00 | 3.07 | 0.62 | 0.00 | 0.01 | 0.00 | 15.09 |
| deepseek/deepseek-v4-flash | 0.00 | 0.76 | 0.00 | 2.14 | 0.37 | 0.00 | 0.01 | 0.00 | 3.73 |
| google/gemini-3.5-flash-lite | 0.00 | 0.70 | 0.00 | 0.86 | 0.25 | 0.00 | 0.00 | 0.00 | 1.15 |

### Ablations (xiaomi/mimo-v2.6-flash)

Source: `evals/results/20261110T080559Z_llm.json` (run 2026-11-10T08:05:59+00:00, git commit: 93db1378cd83aef8d6f69732a477aa2742d5641c). Provider: openrouter. 14 samples x 3 runs per configuration. Judge model: xiaomi/mimo-v2.6-pro. Token prices: openrouter live.

| Configuration | Recs / review | Share with source | Rewrites / review | Median (s) | LLM calls | USD / review | Faithfulness | Answer relevancy |
|---|---|---|---|---|---|---|---|---|
| full | 2.12 | 0.99 | 0.00 | 22.35 | 2.86 | 0.00079 | 0.98 | 0.98 |
| no_rag | 2.07 | 0.00 | 0.00 | 10.80 | 1.00 | 0.00035 | n/a | n/a |
| no_rewrite | 2.24 | 0.94 | 0.00 | 28.67 | 2.88 | 0.00084 | n/a | n/a |

![Ablations](docs/img/ablations.png)
