### Deterministic parts (no LLM)

Source: `evals/results/20261110T081110Z_deterministic.json`. 14 samples.

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

Source: `evals/results/20261110T141250Z_llm.json`. Provider: openrouter. 14 samples x 3 runs per configuration. Judge model: openai/gpt-5-mini. Token prices: openrouter live.

**Quality** (configuration `full`):

| Model | Reviews | Security recall | Security precision | Critical on clean | Injection intact | Recs / review | Share with source | Faithfulness | Answer relevancy | Ragas context precision | Ragas faithfulness | Reviews judged (Ragas) | LLM fallback rate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| xiaomi/mimo-v2.6-flash | 42 | 1.00 | 1.00 | 0 | 1.00 | 2.24 | 0.93 | 0.95 | 0.92 | 0.98 | 0.49 | 12 | 0.00 |
| deepseek/deepseek-v4-flash | 42 | 1.00 | 1.00 | 0 | 1.00 | 1.57 | 0.91 | 0.97 | 0.96 | 1.00 | 0.55 | 9 | 0.00 |
| google/gemini-3.5-flash-lite | 42 | 1.00 | 1.00 | 0 | 1.00 | 0.62 | 1.00 | 0.99 | 0.92 | 0.93 | 0.49 | 7 | 0.00 |

**Speed and cost** (configuration `full`):

| Model | Median (s) | p95 (s) | Deterministic steps (s) | LLM steps (s) | LLM calls | Input tokens | Output tokens | USD / review |
|---|---|---|---|---|---|---|---|---|
| xiaomi/mimo-v2.6-flash | 20.25 | 46.61 | 0.74 | 19.27 | 2.88 | 3608 | 1121 | 0.00082 |
| deepseek/deepseek-v4-flash | 19.61 | 68.39 | 0.92 | 19.11 | 2.83 | 3284 | 2414 | 0.00074 |
| google/gemini-3.5-flash-lite | 3.28 | 4.51 | 0.32 | 2.80 | 2.71 | 3029 | 230 | 0.00148 |

![Speed, cost and recommendation quality per model](docs/img/models.png)

**Median seconds per graph node:**

| Model | cost_estimate | grade_docs | parse | plan_research | retrieve | rewrite_query | save_feedback | security_check | write_report |
|---|---|---|---|---|---|---|---|---|---|
| xiaomi/mimo-v2.6-flash | 0.00 | 2.86 | 0.00 | 2.21 | 0.72 | 0.00 | 0.01 | 0.00 | 7.74 |
| deepseek/deepseek-v4-flash | 0.00 | 1.97 | 0.01 | 3.21 | 0.91 | 0.00 | 0.01 | 0.00 | 6.22 |
| google/gemini-3.5-flash-lite | 0.00 | 0.79 | 0.00 | 0.89 | 0.31 | 0.00 | 0.01 | 0.00 | 1.19 |

### Ablations (xiaomi/mimo-v2.6-flash)

Source: `evals/results/20261110T080559Z_llm.json`. Provider: openrouter. 14 samples x 3 runs per configuration. Judge model: xiaomi/mimo-v2.6-pro. Token prices: openrouter live.

| Configuration | Recs / review | Share with source | Rewrites / review | Median (s) | LLM calls | USD / review | Faithfulness | Answer relevancy |
|---|---|---|---|---|---|---|---|---|
| full | 2.12 | 0.99 | 0.00 | 22.35 | 2.86 | 0.00079 | 0.98 | 0.98 |
| no_rag | 2.07 | 0.00 | 0.00 | 10.80 | 1.00 | 0.00035 | n/a | n/a |
| no_rewrite | 2.24 | 0.94 | 0.00 | 28.67 | 2.88 | 0.00084 | n/a | n/a |

![Ablations](docs/img/ablations.png)

### Graph agent against a ReAct baseline (google/gemini-3.5-flash-lite)

Source: `evals/results/20261110T115819Z_llm.json`. Provider: openrouter. 14 samples x 3 runs per configuration. Judge model: openai/gpt-5-mini. Token prices: openrouter live.

**Security and recommendations:**

| Agent | Reviews ok / run | Security recall | Security precision | Critical on clean | Injection intact | Security tool skipped | Recs / review | Share with source | Links outside the store |
|---|---|---|---|---|---|---|---|---|---|
| Graph agent | 42 / 42 | 1.00 | 1.00 | 0 | 1.00 | n/a | 0.64 | 1.00 | 0 |
| ReAct baseline | 42 / 42 | 1.00 | 0.95 | 0 | 1.00 | 0 | 0.36 | 1.00 | 3 |

**Judged quality** (DeepEval on the whole advisory text, Ragas on the RAG step):

| Agent | Reviews judged (DeepEval) | Faithfulness | Answer relevancy | Reviews judged (Ragas) | Ragas context precision | Ragas faithfulness |
|---|---|---|---|---|---|---|
| Graph agent | 14 | 1.00 | 0.93 | 8 | 1.00 | 0.66 |
| ReAct baseline | 14 | 1.00 | 0.96 | 5 | 0.63 | 0.49 |

**Speed and cost:**

| Agent | Median (s) | p95 (s) | LLM calls | Input tokens | Output tokens | USD / review |
|---|---|---|---|---|---|---|
| Graph agent | 3.13 | 5.91 | 2.79 | 3135 | 239 | 0.00154 |
| ReAct baseline | 2.90 | 4.32 | 2.00 | 2428 | 545 | 0.00209 |

![Graph agent against the ReAct baseline](docs/img/react.png)

### What the LLM adds

Source: `evals/results/20261110T175350Z_llm_value.json`, built with no model calls by `evals/llm_value.py` from `evals/results/20261110T141250Z_llm.json` and a review of the same 14 samples with no LLM. Without an LLM those 14 reviews contain 35 security findings, 14 cost estimates, 0 recommendations and 0 written summaries. Security findings and cost estimates are the same with an LLM, by construction.

| Report | Reviews | Summary written | Recs / review | Share with source | Share naming the configuration | Median (s) | LLM calls | USD / review |
|---|---|---|---|---|---|---|---|---|
| No LLM (rules and cost estimate only) | 14 | no | 0.00 | n/a | n/a | 0.21 | 0 | 0.00000 |
| xiaomi/mimo-v2.6-flash | 42 | yes | 2.24 | 0.93 | 0.62 | 20.25 | 2.88 | 0.00082 |
| deepseek/deepseek-v4-flash | 42 | yes | 1.57 | 0.91 | 0.62 | 19.61 | 2.83 | 0.00074 |
| google/gemini-3.5-flash-lite | 42 | yes | 0.62 | 1.00 | 0.62 | 3.28 | 2.71 | 0.00148 |

"Share naming the configuration" is the share of recommendations whose text names a value from that resource's own configuration or a block it lacks. It is a word match on the text saved for the first run of each sample (recommendations measured: 34 (xiaomi/mimo-v2.6-flash), 24 (deepseek/deepseek-v4-flash), 8 (google/gemini-3.5-flash-lite)), not a judgement of whether the advice is right.

**Time per LLM step** (median seconds when the step ran, and the share of reviews in which it ran):

| Model | LLM calls / review | plan_research (s) | ran in | grade_docs (s) | ran in | write_report (s) | ran in |
|---|---|---|---|---|---|---|---|
| xiaomi/mimo-v2.6-flash | 2.88 | 2.21 | 1.00 | 3.45 | 0.88 | 7.74 | 1.00 |
| deepseek/deepseek-v4-flash | 2.83 | 3.21 | 1.00 | 10.02 | 0.69 | 6.22 | 1.00 |
| google/gemini-3.5-flash-lite | 2.71 | 0.89 | 1.00 | 0.90 | 0.62 | 1.19 | 1.00 |

**Recommendations that name the configuration** (per model, the sourced ones naming the most terms, chosen by code):

- **xiaomi/mimo-v2.6-flash**, `clean/gcs_clean.tf` (names `NEARLINE`, `lifecycle rule`, `autoclass`):
  > google_storage_bucket.reports: The bucket uses a fixed NEARLINE class with no lifecycle rule and no autoclass, so access patterns are not adapted automatically. If the reports access pattern is unknown or mixed, enable Autoclass on the bucket so objects move between classes automatically without needing explicit lifecycle rules; if the pattern is predictable, prefer explicit lifecycle rules instead.
- **xiaomi/mimo-v2.6-flash**, `mixed/web_stack.tf` (names `COLDLINE`, `lifecycle rule`, `autoclass`):
  > google_storage_bucket.uploads: All uploads are written straight to COLDLINE with no lifecycle rule and no Autoclass, so frequently read objects incur retrieval fees and a 90-day minimum storage duration charge if they are deleted or rewritten early. Enable Autoclass on the bucket (or use Standard storage for recent uploads with a lifecycle rule that moves them to Coldline after 90 days) so objects only pay the colder-class price once they stop being read.
- **deepseek/deepseek-v4-flash**, `mixed/web_stack.tf` (names `e2-standard-2`, `pd-balanced`):
  > google_compute_instance.app: The e2-standard-2 machine type may be oversized for a web server workload, and the boot disk is pd-balanced which is more expensive than pd-standard for boot disks. Consider using a smaller shared-core type like e2-medium if the workload is bursty, and change the boot disk to pd-standard to reduce cost.
- **deepseek/deepseek-v4-flash**, `mixed/web_stack.tf` (names `COLDLINE`, `autoclass`):
  > google_storage_bucket.uploads: The bucket uses Coldline storage class but has no lifecycle rules or Autoclass, which may lead to unnecessary costs if data is accessed more frequently than once a quarter. Add lifecycle rules to transition objects to a colder class after 90 days, or enable Autoclass if the access pattern is unpredictable.
- **google/gemini-3.5-flash-lite**, `vulnerable/sql_open.tf` (names `REGIONAL`):
  > google_sql_database_instance.main: The instance uses regional high availability, which doubles the compute and storage costs and may be unnecessary for non-production workloads. Switch the availability type to ZONAL if this is a development, test, or staging database that does not require an availability target, which will roughly halve the cost.
- **google/gemini-3.5-flash-lite**, `vulnerable/compute_open_ssh.tf` (names `n2-standard-4`):
  > google_compute_instance.web: The instance uses an N2 machine type which has higher per-core performance at a higher price, whereas E2 machine types are the lowest-cost general-purpose family suitable for web servers. Switch the machine type from n2-standard-4 to an E2 family type to lower the price.
