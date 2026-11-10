# Progress

Last updated: 2026-11-09

| Phase | Status | Notes |
|---|---|---|
| 0 Project setup | Done | `uv sync`, layout, ruff, pytest |
| 1 Deterministic tools | Done | Parser, 20 rules, cost estimator, Billing API client, dataset of 14 samples |
| 2 RAG | Done | 34 documents, 68 chunks, local embeddings |
| 3 Memory | Done | SQLite store, feedback policy |
| 4 Agent graph | Done | 10 nodes, rewrite loop capped at 2, interrupt for human review |
| 5 Interfaces | Done | MCP tool and Streamlit UI |
| 6 Evaluation | **Partly done** | Deterministic results saved. LLM evaluation not run yet (needs an API key) |
| 7 Documentation | **Partly done** | Everything written except the model comparison, which waits for phase 6 |

## What is left

1. **Run the LLM evaluation.** Put `OPENROUTER_API_KEY` in `.env`, then:
   ```bash
   uv run python -m evals.run
   uv run python -m evals.report
   ```
   This fills the "Full agent, per model" and "Ablations" sections of the README.
2. **Write the discussion of the model results** in the README once the numbers exist.
3. **Check the code paths that have only run against fakes**, with a real key:
   - the OpenRouter client settings in `agent/llm.py` (JSON mode, temperature, seed)
   - the DeepEval judge in `evals/judge.py`
   - LangSmith tracing (set `LANGSMITH_API_KEY`)
   - the live Billing Catalog API in `tools/billing_api.py` (set `GCP_BILLING_API_KEY`)
4. **Review the static prices** in `tools/prices_static.json` against the current GCP
   price list. They were entered by hand as approximate values.
5. **First git commit.** The result files currently record "no commits yet". After the
   first commit, rerun the evals so the results carry a commit hash.

## Verification at the time of writing

- `uv run pytest`: all tests pass, with no API key (the LLM is faked at the boundary).
- `uv run ruff check .`: no errors.
- Deterministic eval: `evals/results/20261109T201508Z_deterministic.json`.
