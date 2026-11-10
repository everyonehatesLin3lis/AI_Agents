import pytest

from rag.ingest import load_chunks
from rag.retriever import RetrieverError, search_gcp_docs


def test_finds_the_relevant_document_and_its_source(chroma_dir):
    docs = search_gcp_docs("database accepts connections from any IP address", store_dir=chroma_dir)

    assert docs[0].id.startswith("cloud_sql/authorize-networks")
    assert docs[0].source_url == "https://cloud.google.com/sql/docs/mysql/authorize-networks"
    assert "0.0.0.0/0" in docs[0].text


def test_service_filter_limits_results_to_that_service(chroma_dir):
    docs = search_gcp_docs("reduce cost with spot capacity", service="gke", store_dir=chroma_dir)

    assert docs
    assert {doc.service for doc in docs} == {"gke"}


def test_returns_k_results_ordered_by_similarity(chroma_dir):
    docs = search_gcp_docs("cheaper storage for rarely read data", k=3, store_dir=chroma_dir)

    assert len(docs) == 3
    assert [doc.score for doc in docs] == sorted((doc.score for doc in docs), reverse=True)


def test_empty_query_returns_nothing(chroma_dir):
    assert search_gcp_docs("   ", store_dir=chroma_dir) == []


def test_missing_store_raises_a_clear_error(tmp_path):
    with pytest.raises(RetrieverError, match="rag.ingest"):
        search_gcp_docs("anything", store_dir=tmp_path / "not-built")


def test_every_chunk_has_a_google_cloud_source_url():
    chunks = load_chunks()

    assert len(chunks) >= 60
    assert all(chunk.source_url.startswith("https://cloud.google.com/") for chunk in chunks)
    assert {chunk.service for chunk in chunks} == {
        "cloud_storage",
        "cloud_sql",
        "compute",
        "cloud_run",
        "gke",
    }
