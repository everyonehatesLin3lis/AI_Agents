# RAG source documents

Each file is a short set of notes on one Google Cloud documentation page, written for
this project. The front matter records the official page (`source_url`), which is what
the agent cites. The notes are a condensed summary, not a copy of the page, and Google's
documentation is the authority if the two ever disagree.

```
---
title: Public access prevention
service: cloud_storage        # one of: cloud_storage, cloud_sql, compute, cloud_run, gke
source_url: https://cloud.google.com/storage/docs/public-access-prevention
---

## Section heading

Text of the section. Each `##` section becomes one chunk in the vector store.
```

To add a document: create a file in the matching service folder with the same front
matter, then rebuild the store with `uv run python -m rag.ingest`.

This README is not ingested (it has no front matter).
