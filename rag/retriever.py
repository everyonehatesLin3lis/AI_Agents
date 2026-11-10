"""Search the GCP documentation store.

`search_gcp_docs(query, service)` is the seam the agent uses. It returns `Doc` objects
that always carry a `source_url`, so anything the agent says based on a document can be
cited. Embeddings are computed locally by Chroma's default model (all-MiniLM-L6-v2), so
retrieval needs no API key and costs nothing.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import chromadb

from rag.ingest import COLLECTION_NAME, DEFAULT_STORE_DIR
from tools.models import Doc

DEFAULT_K = 4


class RetrieverError(Exception):
    """The document store cannot be searched. The message is safe to show to users."""


@lru_cache(maxsize=4)
def _collection(store_dir: str) -> Any:
    if not Path(store_dir).exists():
        raise RetrieverError(
            "The documentation store has not been built. Run: uv run python -m rag.ingest"
        )
    try:
        return chromadb.PersistentClient(path=store_dir).get_collection(COLLECTION_NAME)
    except Exception as exc:  # chroma raises different types across versions
        raise RetrieverError(
            "The documentation store is missing or unreadable. Run: uv run python -m rag.ingest"
        ) from exc


def search_gcp_docs(
    query: str,
    service: str | None = None,
    k: int = DEFAULT_K,
    store_dir: Path = DEFAULT_STORE_DIR,
) -> list[Doc]:
    """Return the `k` chunks most similar to `query`, optionally limited to one service."""
    if not query.strip():
        return []
    collection = _collection(str(store_dir))
    try:
        result = collection.query(
            query_texts=[query],
            n_results=k,
            where={"service": service} if service else None,
        )
    except Exception as exc:
        raise RetrieverError(f"Documentation search failed ({type(exc).__name__}).") from exc
    return [
        Doc(
            id=doc_id,
            title=f"{meta['title']}: {meta['section']}",
            service=meta["service"],
            source_url=meta["source_url"],
            text=meta["text"],
            score=round(1 - distance, 4),
        )
        for doc_id, meta, distance in zip(
            result["ids"][0], result["metadatas"][0], result["distances"][0], strict=True
        )
    ]
