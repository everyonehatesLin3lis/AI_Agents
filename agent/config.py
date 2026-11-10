"""Runtime settings. Nothing here is hard-coded in the nodes: the model, temperature,
seed and every switch used for ablations come from a `Settings` object.

Defaults can be overridden with environment variables (see `.env.example`) or, in the
UI, from the Developer section.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_MODEL = "openai/gpt-6-luna"


class Settings(BaseModel):
    # LLM
    model: str = DEFAULT_MODEL
    temperature: float | None = 0.0  # None = do not send the parameter
    seed: int | None = 42  # None = do not send the parameter
    llm_timeout_s: float = 60.0
    llm_max_retries: int = 2
    extra_instructions: str = ""  # developer-only addition to the report prompt

    # Research loop (also the ablation switches)
    use_rag: bool = True
    max_rewrites: int = Field(default=2, ge=0, le=2)
    max_queries: int = Field(default=4, ge=1, le=8)
    retrieval_k: int = Field(default=4, ge=1, le=10)
    min_relevant_docs: int = Field(default=2, ge=1)

    # Cost estimate
    default_region: str = "us-central1"
    assumed_storage_gb: float = 100.0

    # Local data (vector store, SQLite)
    data_dir: Path = Path("data")

    @property
    def chroma_dir(self) -> Path:
        return self.data_dir / "chroma"

    @property
    def memory_path(self) -> Path:
        return self.data_dir / "memory.sqlite"

    @classmethod
    def from_env(cls) -> Settings:
        """Build settings from environment variables, falling back to the defaults."""
        values: dict[str, object] = {}
        if model := os.getenv("REVIEW_MODEL"):
            values["model"] = model
        if "REVIEW_TEMPERATURE" in os.environ:
            raw = os.environ["REVIEW_TEMPERATURE"].strip()
            values["temperature"] = float(raw) if raw else None
        if "REVIEW_SEED" in os.environ:
            raw = os.environ["REVIEW_SEED"].strip()
            values["seed"] = int(raw) if raw else None
        if data_dir := os.getenv("REVIEW_DATA_DIR"):
            values["data_dir"] = Path(data_dir)
        return cls(**values)
