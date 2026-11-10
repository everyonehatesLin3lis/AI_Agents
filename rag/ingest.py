"""Build the Chroma vector store from the Markdown files in `rag/docs/`.

Run with:  uv run python -m rag.ingest

Each `##` section of a document becomes one chunk. Sections are short and cover one idea,
so a chunk is a complete thought and carries the `source_url` of the page it came from.
"""

from __future__ import annotations

import re
from pathlib import Path

import chromadb
from pydantic import BaseModel

DOCS_DIR = Path(__file__).parent / "docs"
DEFAULT_STORE_DIR = Path("data") / "chroma"
COLLECTION_NAME = "gcp_docs"
_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)
_SECTION = re.compile(r"^## +(.+)$", re.M)


class Chunk(BaseModel):
    id: str
    title: str
    service: str
    source_url: str
    section: str
    text: str


class IngestError(Exception):
    pass


def load_chunks(docs_dir: Path = DOCS_DIR) -> list[Chunk]:
    """Read every document with front matter and split it into section chunks."""
    chunks: list[Chunk] = []
    for path in sorted(docs_dir.rglob("*.md")):
        chunks.extend(_split_document(path))
    if not chunks:
        raise IngestError(f"No documents with front matter found in {docs_dir}.")
    return chunks


def _split_document(path: Path) -> list[Chunk]:
    match = _FRONT_MATTER.match(path.read_text(encoding="utf-8").replace("\r\n", "\n"))
    if not match:
        return []  # e.g. the README
    meta = dict(line.split(": ", 1) for line in match.group(1).splitlines() if ": " in line)
    parts = _SECTION.split(match.group(2))  # [preamble, heading, text, heading, text, ...]
    chunks = []
    for index in range(1, len(parts) - 1, 2):
        heading, text = parts[index].strip(), parts[index + 1].strip()
        chunks.append(
            Chunk(
                id=f"{meta['service']}/{path.stem}#{(index + 1) // 2}",
                title=meta["title"],
                service=meta["service"],
                source_url=meta["source_url"],
                section=heading,
                text=text,
            )
        )
    return chunks


def build_store(store_dir: Path = DEFAULT_STORE_DIR, docs_dir: Path = DOCS_DIR) -> int:
    """(Re)build the collection and return the number of chunks stored."""
    chunks = load_chunks(docs_dir)
    client = chromadb.PersistentClient(path=str(store_dir))
    if COLLECTION_NAME in [collection.name for collection in client.list_collections()]:
        client.delete_collection(COLLECTION_NAME)
    collection = client.create_collection(COLLECTION_NAME, metadata={"hnsw:space": "cosine"})
    collection.add(
        ids=[chunk.id for chunk in chunks],
        # The title and heading are embedded with the text so short sections keep context.
        documents=[f"{chunk.title}. {chunk.section}. {chunk.text}" for chunk in chunks],
        metadatas=[chunk.model_dump(exclude={"id"}) for chunk in chunks],
    )
    return len(chunks)


if __name__ == "__main__":
    count = build_store()
    print(f"Stored {count} chunks in {DEFAULT_STORE_DIR / COLLECTION_NAME}")
