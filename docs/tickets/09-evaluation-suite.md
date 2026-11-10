# 09: Evaluation suite with saved, reproducible results

**What to build:** One command measures the agent on a fixed dataset and saves the raw results with the model, date and git commit. A second command turns the saved results into the README tables and charts.

**Blocked by:** 05, 06, 08

**Status:** in progress

- [x] Deterministic metrics: security precision, recall, F1; cost error; retrieval hit rate; tool speed (done)
- [ ] LLM metrics per model: source share, faithfulness, relevancy, latency median and p95, tokens, cost (code done and tested with a fake LLM)
- [ ] Ablations: without RAG, without the rewrite loop (code done)
- [ ] A saved LLM run for at least three models (waiting for an API key)
- [ ] README results section generated from the saved files (done for the deterministic part)

**Review talking point:** Tests check that the code is correct and use a fake model. Evals measure how good the output is and need a real one. Numbers in the README are generated from saved runs, so none of them can be made up.
