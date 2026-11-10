# 04: Cited cost and sizing recommendations (RAG and the research loop)

**What to build:** The report suggests cheaper, smaller or simpler alternatives. Each suggestion that comes from the documentation carries the link to the page. If the first search finds too little, the agent rewrites its queries and tries again, at most twice.

**Blocked by:** 02, 03

**Status:** done

- [x] Documentation store built from notes that each carry a source URL
- [x] plan_research, retrieve, grade_docs, rewrite_query and write_report nodes in the graph
- [x] The rewrite loop stops after 2 attempts
- [x] A recommendation without a document is labelled as a suggestion
- [x] The agent works, with a warning, when the store or the LLM is unavailable

**Review talking point:** This is the agentic part: the model decides what to look up, judges what it found and may try again. The loop has a hard limit in code, so the model's freedom is bounded.
