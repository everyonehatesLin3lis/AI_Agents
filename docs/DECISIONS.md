# Decisions

Short records of the technical choices that shape the project. Each one says what was
decided, why, and what was given up. New decisions go at the end.

## 1. Terraform only, five services

**Decision.** The input is Terraform text. The services are Cloud Run, Compute Engine,
Cloud SQL, Cloud Storage and GKE. Other resource types are listed as "not reviewed".

**Why.** A narrow scope can be tested properly. Terraform is declarative, so the whole
configuration is visible before anything runs, which is exactly when a review helps.

**Given up.** gcloud scripts, Pulumi and the many other GCP services.

## 2. Security findings are deterministic

**Decision.** Security findings come from fixed rules in code. The LLM cannot create,
remove or change them, and neither can feedback or memory.

**Why.** A security review has to give the same answer every time, be explainable line
by line, and be immune to text hidden in the file under review. An LLM offers none of
those. Rules also cost nothing and run in well under a millisecond.

**Given up.** Rules only catch what someone wrote a rule for. An LLM might notice an
unusual problem that no rule covers. The advisory section can still mention such
things, but only as cost, sizing or simplification suggestions.

## 3. The LLM never sees the raw Terraform

**Decision.** Prompts contain a summary built from a fixed list of sizing attributes
per resource type. Free-text fields are never included.

**Why.** Defence in depth against prompt injection. Removing the text is stronger than
telling the model to ignore it. It also keeps prompts short and cheap.

**Given up.** The LLM cannot comment on anything outside the list, for example a
startup script. Adding an attribute means editing `agent/summary.py`.

## 4. JSON mode with our own validation, not provider tool calling

**Decision.** Each LLM step asks for a JSON object, and `agent/llm.py` validates it
against a Pydantic model, with one repair attempt.

**Why.** It works the same way across vendors behind OpenRouter, and with the fake
model used in tests. Validation is in one place, and the schema itself is a guard: the
report schema has no "security" category and no "critical" severity.

**Given up.** Native structured outputs can be stricter on models that support them.

## 5. LangGraph for orchestration

**Decision.** The review is a LangGraph state graph with typed (Pydantic) state.

**Why.** The flow has a bounded loop and a pause for human input. LangGraph provides
both (conditional edges, `interrupt` with a checkpointer) and makes the control flow a
visible structure that can be tested without an LLM.

**Given up.** A plain function pipeline would be less code for the straight path, but
the loop and the pause would have to be written by hand.

## 6. Chroma with local embeddings

**Decision.** Chroma as the vector store, with its default local embedding model
(all-MiniLM-L6-v2).

**Why.** Runs in-process from a folder, with no server. Local embeddings mean retrieval
needs no API key, costs nothing and gives the same result on every run, which matters
for reproducible evals. The store is small (68 chunks), so a larger system such as
pgvector would add operations work for no gain.

**Given up.** Hosted embedding models are stronger on hard queries. On this corpus the
local model already finds the expected document for nearly every test query.

## 7. Documentation as curated notes

**Decision.** `rag/docs/` holds short notes written for this project, one file per
Google Cloud page, each with the page's URL.

**Why.** Scraped pages are long and full of navigation and unrelated sections, which
hurts retrieval. Short single-topic sections make clean chunks. The URL is still the
official page, so a citation leads the reader to the authority.

**Given up.** The notes can go out of date and are only as good as their author. They
are a summary, not the source.

## 8. SQLite for memory

**Decision.** One SQLite file holds project constraints, feedback and review history.

**Why.** Single user, single machine, a handful of rows per review. No server, and the
standard library is enough.

**Given up.** Concurrent multi-user access. A hosted deployment would need Postgres.

## 9. Feedback can only deprioritise

**Decision.** Dismissing a cost or sizing suggestion marks later suggestions of the
same kind as deprioritised and sorts them last. Nothing is removed. Feedback on a
security finding is stored but has no effect.

**Why.** The user should be able to say "not relevant here" without being able to
switch off the reviewer. Keeping the item visible means a wrong dismissal is not
silent.

**Given up.** A user cannot fully hide a suggestion they are tired of.

## 10. OpenRouter as the LLM provider

**Decision.** The agent uses OpenRouter when `OPENROUTER_API_KEY` is set, and OpenAI
directly otherwise. Both go through `langchain-openai`.

**Why.** One key gives access to models from several vendors, which the model
comparison needs. OpenRouter speaks the OpenAI API, so no new dependency was added. It
also publishes prices per model, which the eval runner records with each run.

**Given up.** One more company in the request path, and small differences in which
parameters each model honours (temperature and seed are sent, and a model that does
not support them ignores them).

## 11. Static prices first, live prices for Compute Engine only

**Decision.** The estimator works from `tools/prices_static.json`. When a billing API
key is set, live Compute Engine prices (vCPU, memory, disks) replace the static ones.
Evals always use the static table.

**Why.** The agent must work with no credentials. Compute Engine SKUs are the simplest
to map reliably and also price GKE nodes. Static prices in evals keep cost results
identical from run to run.

**Given up.** Live prices for Cloud SQL, Cloud Storage and Cloud Run. The report says
when prices may be outdated.

## 12. Human review as a graph interrupt

**Decision.** `human_review` calls `interrupt()`. The UI resumes the graph with the
feedback. The MCP tool and the evals run with `interactive=False` and skip the pause.

**Why.** The pause is part of the agent's flow and is saved by the checkpointer, so
the review continues from where it stopped. A coding agent calling the MCP tool needs
an answer in one call, so the pause is optional.

**Given up.** The checkpointer is in memory, so a paused review is lost if the UI
process restarts.

## 13. MCP SDK 2.x

**Decision.** The server uses `MCPServer` from the MCP Python SDK 2.x.

**Why.** It is the current SDK. `FastMCP`, named in the original project notes, was
renamed to `MCPServer` in version 2. The decorator API is the same.

## 14. Three low-cost models, judged by a fourth vendor

**Decision.** The model comparison uses `xiaomi/mimo-v2.6-flash`,
`deepseek/deepseek-v4-flash` and `google/gemini-3.5-flash-lite`, judged by
`openai/gpt-5-mini`. The ablations were run once, on MiMo-flash only.

**Why.** The project owner chose these models and a $5 budget for all runs. Three
vendors give the comparison some spread. A judge from a fourth vendor means no model
is scored by a relative. The full set of runs cost under $1.

**Given up.** No premium model, so the results cannot say what paying more buys. The
ablation run used `xiaomi/mimo-v2.6-pro` as judge (a relative of the judged model)
because it ran before the judge was chosen; it was not repeated, to save cost.

## 15. Exact regional prices in the static table

**Decision.** `tools/prices_static.json` stores exact Compute Engine and disk prices
for its 8 regions, copied from the live Billing Catalog API on 2026-11-10. Other
services keep a us-central1 price times a region multiplier.

**Why.** A check against the live API showed the hand-typed us-central1 prices were
right, but the 1.1 Europe multiplier overpriced disks by 10%: Google charges the same
disk price in us-central1 and europe-west1. Exact values remove that error for the
resources the API covers, while the evals still use a fixed table.

**Given up.** The snapshot does not update itself. It has to be refreshed by hand,
and the expected costs in `evals/dataset/` recalculated.
