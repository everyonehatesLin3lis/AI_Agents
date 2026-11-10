# Progress

Last updated: 2026-11-10

| Phase | Status | Notes |
|---|---|---|
| 0 Project setup | Done | `uv sync`, layout, ruff, pytest |
| 1 Deterministic tools | Done | Parser, 20 rules, cost estimator, Billing API client, dataset of 14 samples |
| 2 RAG | Done | 34 documents, 68 chunks, local embeddings |
| 3 Memory | Done | SQLite store, feedback policy |
| 4 Agent graph | Done | 10 nodes, rewrite loop capped at 2, interrupt for human review |
| 5 Interfaces | Done | MCP tool and Streamlit UI |
| 6 Evaluation | Done | Deterministic run, 3-model comparison, MiMo ablations (all in `evals/results/`) |
| 7 Documentation | Done | README results and discussion written from the saved runs |

## Done on 2026-11-10

- First commit and push to GitHub (`main`).
- Checked with real keys: OpenRouter (JSON mode, temperature, seed), the DeepEval
  judge, LangSmith tracing and the live Billing Catalog API.
- Static prices checked against the live API. Compute Engine and disk prices for 8
  regions are now exact (decision 15). Expected costs recalculated by hand.
- Cost estimate: `default_region` and `regions_used` instead of one misleading
  `region`; multi-region buckets say how they were priced.
- LLM evaluation: MiMo-flash with ablations (judge MiMo-pro), then MiMo-flash,
  DeepSeek-v4-flash and Gemini-3.5-flash-lite (judge GPT-5 mini). Total OpenRouter
  spend under $1.
- `evals/report.py` takes the model comparison and the ablations from their own latest
  runs, each with its own source line.
- Architecture review: `docs/reviews/architecture-2026-11-10.md`, with a status update.

## What is left (optional)

1. **Architecture candidate 6:** `regions_used` records the region asked for, not the
   one whose prices were used. A VM in an unknown region (e.g. `me-west1`) shows
   "priced in: me-west1" next to a note saying us-central1 prices were used.
2. **Architecture candidates 1 and 2:** LLM fallbacks as structured data instead of
   warning text; one place that calculates review cost.
3. **A total deadline per LLM step.** One review waited 628 s (see README, Discussion).
4. **The app default model** (`agent/config.py`, `openai/gpt-6-luna`) was not part of
   the evaluation. The evaluation favours `google/gemini-3.5-flash-lite` for the UI and
   MCP tool.
5. A premium model in the comparison, and ablations on a second model.

## Verification at the time of writing

- `uv run pytest`: all tests pass, with no API key (the LLM is faked at the boundary).
- `uv run ruff check .`: no errors.
- Results: `evals/results/20261110T081110Z_deterministic.json`,
  `20261110T080559Z_llm.json` (ablations), `20261110T095622Z_llm.json` (comparison).
