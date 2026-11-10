"""The things the graph depends on, gathered in one object.

Nodes never create their own LLM client, database connection or HTTP client. They get
them from `Deps`. That is what makes the graph testable: a test passes a fake chat model
and a temporary database, and every node and tool in between is the real one.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from langchain_core.language_models import BaseChatModel

from agent.config import Settings
from agent.llm import get_chat_model
from memory.store import MemoryStore
from rag.retriever import search_gcp_docs
from tools.billing_api import BillingCatalogClient, load_prices
from tools.models import Doc
from tools.pricing import PriceTable

SearchFn = Callable[[str, str | None, int], list[Doc]]
PROMPTS_DIR = Path(__file__).parent / "prompts"


@dataclass
class Deps:
    settings: Settings
    llm: BaseChatModel | None
    store: MemoryStore
    search: SearchFn
    billing_client: BillingCatalogClient | None = None
    clock: Callable[[], float] = time.perf_counter
    _prices: PriceTable | None = field(default=None, repr=False)

    def prices(self) -> PriceTable:
        """Load prices once per `Deps` object (the Billing API call is slow)."""
        if self._prices is None:
            self._prices = load_prices(self.billing_client)
        return self._prices

    def prompt(self, name: str) -> str:
        """Load a prompt template from `agent/prompts/<name>.md`."""
        return (PROMPTS_DIR / f"{name}.md").read_text(encoding="utf-8")


def default_deps(settings: Settings | None = None) -> Deps:
    """Production wiring: real LLM (if a key is set), real store, real retriever."""
    settings = settings or Settings.from_env()
    billing_key = os.getenv("GCP_BILLING_API_KEY", "").strip()
    return Deps(
        settings=settings,
        llm=get_chat_model(settings),
        store=MemoryStore(settings.memory_path),
        search=lambda query, service, k: search_gcp_docs(
            query, service, k, store_dir=settings.chroma_dir
        ),
        billing_client=BillingCatalogClient(billing_key) if billing_key else None,
    )
