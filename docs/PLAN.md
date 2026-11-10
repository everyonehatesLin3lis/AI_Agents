# Plan

The project is built in phases. Each phase has a "done when" check. A phase is finished
only when that check passes and `uv run pytest` and `uv run ruff check .` are both
green. Progress is tracked in `PROGRESS.md`.

The phases below are horizontal (one layer each) because that is the clearest way to
explain the system. The work itself was sliced vertically: see `tickets/`, which start
with a walking skeleton (Terraform in, one finding shown in the UI).

## Phase 0: Project setup

`pyproject.toml`, `uv sync`, repository layout, `.gitignore`, `.env.example`, ruff and
pytest configuration.

**Done when:** `uv sync` works on a clean checkout and `uv run pytest` runs.

## Phase 1: Deterministic tools

- `tools/tf_parser.py`: input validation (not Terraform, over 200 KB) and parsing.
- `tools/security_rules.py`: the rule registry and `check_security`.
- `tools/cost_estimator.py`, `tools/pricing.py`, `tools/prices_static.json`.
- `tools/billing_api.py`: Billing Catalog client with timeout, retry and fallback.
- `evals/dataset/`: Terraform samples, labelled findings, hand-calculated costs.

**Done when:** every tool has unit tests that use the dataset; security recall is at
least 0.9 with zero critical false positives on the clean samples; cost totals match
the hand-calculated values.

## Phase 2: RAG

- `rag/docs/`: notes on Google Cloud documentation pages, each with its source URL.
- `rag/ingest.py` builds the Chroma store. `rag/retriever.py` exposes
  `search_gcp_docs(query, service)`.

**Done when:** retrieval is tested against a real Chroma collection, and every chunk
carries a Google Cloud `source_url`.

## Phase 3: Memory

- `memory/store.py`: project constraints, feedback and review history in SQLite.
- `memory/feedback_policy.py`: feedback may deprioritise cost and sizing suggestions,
  never security findings.

**Done when:** tests show that constraints persist, and that feedback aimed at a
security finding has no effect.

## Phase 4: Agent graph

- `agent/state.py`, one node per file in `agent/nodes/`, prompts in `agent/prompts/`.
- `agent/graph.py` wires the architecture from `CLAUDE.md`, with the rewrite loop
  capped at 2 and an interrupt for human review.
- `agent/report.py` assembles the report and enforces the guards on LLM output.
- Token usage and per-node timing recorded for every review.

**Done when:** integration tests run a full review with a fake LLM, including: the
rewrite cap, the three injection samples, a review with no LLM at all, an LLM that
always fails, and the pause/resume of human review.

## Phase 5: Interfaces

- `mcp_server/server.py`: the `review_gcp_infra` tool.
- `ui/app.py`: Streamlit UI with a separate Developer section, project memory, the
  feedback form, and tokens, cost and time per review.

**Done when:** the MCP tool is tested through the server's own call path, and the UI
is tested with Streamlit's AppTest (Terraform in, finding shown).

## Phase 6: Evaluation

- `evals/run.py`: deterministic metrics always; LLM metrics per model when a key is
  set. Results saved to `evals/results/` with model, date and git commit.
- `evals/judge.py`: DeepEval faithfulness and answer relevancy.
- `evals/report.py`: tables and charts for the README, generated from saved runs.

**Done when:** a deterministic result file exists and the README shows it; an LLM
result file exists for at least three models with the `no_rag` and `no_rewrite`
ablations, and the README shows it.

## Phase 7: Documentation

`README.md` (problem, architecture, setup, usage, method, results, discussion,
limitations, future work), `DECISIONS.md`, `LEARNING_NOTES.md`, `PROGRESS.md`.

**Done when:** every number in the README traces to a file in `evals/results/`, and a
new reader can set up and run the project from the README alone.
