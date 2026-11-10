"""Node 5: search the documentation store for each query. No LLM.

If the store is missing or broken the review continues without documents, and the
report says so. Recommendations without a document are shown as suggestions.
"""

from __future__ import annotations

from typing import Any

from agent.deps import Deps
from agent.state import ReviewState
from rag.retriever import RetrieverError
from tools.models import Doc


def make_retrieve(deps: Deps):
    def retrieve(state: ReviewState) -> dict[str, Any]:
        already_kept = {doc.id for doc in state.relevant_docs}
        found: dict[str, Doc] = {}
        try:
            for query in state.queries:
                for doc in deps.search(query.query, query.service, deps.settings.retrieval_k):
                    if doc.id not in already_kept and doc.id not in found:
                        found[doc.id] = doc
        except RetrieverError as exc:
            return {"docs": [], "errors": [str(exc)], "stop_research": True}
        return {"docs": list(found.values())}

    return retrieve
