"""Shared fixtures.

Only system boundaries are faked: the LLM (a scripted chat model) and the Billing API
(not configured, so the static prices are used). Our own tools, nodes, the Chroma
collection and the SQLite store are real.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from rag.ingest import build_store


class FakeChatModel(BaseChatModel):
    """A chat model that answers by prompt type, so tests do not depend on call order.

    `replies` maps a marker found in the system prompt (e.g. "PLAN_RESEARCH") to a JSON
    serialisable reply, a list of replies used one per call, or an Exception to raise.
    Every call is recorded in `calls` so tests can check what the LLM was shown.
    """

    replies: dict[str, Any] = {}
    calls: list[dict[str, str]] = []
    model_name: str = "fake-model"

    @property
    def _llm_type(self) -> str:
        return "fake"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        system, user = str(messages[0].content), str(messages[-1].content)
        marker = next((m for m in self.replies if m in system), None)
        self.calls.append({"marker": marker or "?", "system": system, "user": user})
        if marker is None:
            raise AssertionError(f"FakeChatModel has no reply for prompt: {system[:80]}")
        reply = self.replies[marker]
        if isinstance(reply, list):
            reply = reply.pop(0) if len(reply) > 1 else reply[0]
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            reply = reply(user)  # lets a test build the reply from what the LLM was shown
        content = reply if isinstance(reply, str) else json.dumps(reply)
        message = AIMessage(
            content=content,
            usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120},
        )
        return ChatResult(generations=[ChatGeneration(message=message)])

    def calls_for(self, marker: str) -> list[dict[str, str]]:
        return [call for call in self.calls if call["marker"] == marker]


@pytest.fixture(autouse=True)
def no_real_api_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests must never call a real API, even when the developer has a .env file.

    The variables are set to empty strings (not deleted) so that `load_dotenv()` does
    not fill them back in from .env.
    """
    for name in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "GCP_BILLING_API_KEY",
                 "LANGSMITH_API_KEY"):  # fmt: skip
        monkeypatch.setenv(name, "")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")


@pytest.fixture(scope="session")
def chroma_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A real Chroma collection built once from rag/docs/ in a temporary folder."""
    store_dir = tmp_path_factory.mktemp("chroma")
    build_store(store_dir)
    return store_dir


@pytest.fixture
def make_deps(tmp_path: Path, chroma_dir: Path):
    """Build real dependencies around a fake LLM: real Chroma, temporary SQLite."""
    from agent.config import Settings
    from agent.deps import Deps
    from memory.store import MemoryStore
    from rag.retriever import search_gcp_docs

    def _make(llm: Any = None, **settings: Any):
        return Deps(
            settings=Settings(data_dir=tmp_path, **settings),
            llm=llm,
            store=MemoryStore(tmp_path / "memory.sqlite"),
            search=lambda query, service, k: search_gcp_docs(
                query, service, k, store_dir=chroma_dir
            ),
            billing_client=None,
        )

    return _make


@pytest.fixture
def make_llm():
    def _make(replies: dict[str, Any]) -> FakeChatModel:
        return FakeChatModel(replies=replies, calls=[])

    return _make
