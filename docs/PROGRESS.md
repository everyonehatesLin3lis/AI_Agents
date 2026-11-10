# Progress

Last updated: 2026-11-10

| Phase | Status | Notes |
|---|---|---|
| 0 Project setup | Done | `uv sync`, layout, ruff, pytest |
| 1 Deterministic tools | Done | Parser, 20 rules, cost estimator, Billing API client, dataset of 14 samples |
| 2 RAG | Done | 34 documents, 68 chunks, local embeddings |
| 3 Memory | Done | SQLite store, feedback policy |
| 4 Agent graph | Done | 10 nodes, rewrite loop capped at 2, interrupt for human review |
| 5 Interfaces | Done | MCP tool, and a Next.js web UI over an HTTP API (replaced Streamlit) |
| 6 Evaluation | Done | Deterministic run, 3-model comparison with DeepEval and Ragas, MiMo ablations, graph against a ReAct baseline (all in `evals/results/`) |
| 7 Documentation | Done | README results, charts and discussion written from the saved runs |

## Done on 2026-11-10

- First commit and push to GitHub (`main`).
- Checked with real keys: OpenRouter (JSON mode, temperature, seed, tool calling), the
  DeepEval and Ragas judges, LangSmith tracing and the live Billing Catalog API.
- Static prices checked against the live API. Compute Engine and disk prices for 8
  regions are now exact (decision 15). Expected costs recalculated by hand.
- Cost estimate: `default_region` and `regions_used` instead of one misleading
  `region`; multi-region buckets say how they were priced. `regions_used` reports the
  region whose prices were actually used (architecture candidate 6).
- Default model is `google/gemini-3.5-flash-lite`, chosen from the comparison.
- README: common use cases with a real saved review, a "what kind of agent" paragraph.
  Learning notes: function calling, agent types, prompt engineering against RAG against
  agents.
- Ragas metrics for the RAG step (decision 17).
- ReAct baseline with function calling, compared with the graph agent (decision 16).
- Eval runner: commit recorded at run start, judged text saved, `evals/rejudge.py`,
  flushed progress output (decision 18).
- Six-panel comparison charts for the models and for graph against ReAct.
- Architecture review: `docs/reviews/architecture-2026-11-10.md`, with a status update.
- Web UI rebuilt in Next.js (decision 19): review service, HTTP API, live progress
  steps, an intro that says what the tool does and does not do. Streamlit removed.
  Checked by clicking through it in a real browser.
- README: run date and commit removed from the result source lines; first-person wording.

## Saved runs the README uses

| File in `evals/results/` | What it is |
|---|---|
| `20261110T081110Z_deterministic.json` | Rules, cost estimator, retrieval, tool speed |
| `20261110T141250Z_llm.json` | Three models, graph agent, DeepEval and Ragas (judge GPT-5 mini) |
| `20261110T080559Z_llm.json` | MiMo ablations: full, no RAG, no rewrite loop (judge MiMo-pro) |
| `20261110T115819Z_llm.json` | Graph agent against the ReAct baseline on Gemini |
| `20261110T095622Z_llm.json` | First three-model run, without Ragas; cited for run-to-run variance and the 628 s fallback |
| `20261110T141250Z_ragas_diagnostic.json` | Check of why Ragas faithfulness is low |

OpenRouter spend for all runs: under $3 of the $5 budget.

## What is left (optional)

1. **Architecture candidates 1 and 2:** LLM fallbacks as structured data instead of
   warning text; one place that calculates review cost.
2. **A total deadline per LLM step.** One review waited 628 s (see README, Discussion).
3. A premium model in the comparison, and ablations on a second model.
4. The ReAct baseline on more models and with harder injection samples.
5. Check whether Turing College created a separate submission repository; the code is
   in my personal repository.
6. Move the MCP server onto `agent/service.py`, so both front ends share one path.
7. Generate the UI's TypeScript types from the Pydantic models instead of writing them
   by hand.

## Verification at the time of writing

- `uv run pytest`: all tests pass, with no API key (the LLM is faked at the boundary).
- `uv run ruff check .`: no errors.
