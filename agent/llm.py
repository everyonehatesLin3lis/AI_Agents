"""Everything that talks to the LLM goes through this module.

- `get_chat_model` builds the client from settings and environment variables. OpenRouter
  is used when `OPENROUTER_API_KEY` is set, otherwise OpenAI directly. Both speak the
  OpenAI API, so the same `langchain-openai` client works for either.
- `call_json` sends one prompt and returns a validated Pydantic object. It is the only
  place where an LLM reply is parsed, so there is one place to look when a model
  misbehaves.

Failure handling: the client has a timeout and retries with backoff (built into
`ChatOpenAI`). A reply that is not valid JSON for the schema gets one repair attempt.
After that `LLMCallError` is raised, and each node has a deterministic fallback.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from agent.config import Settings

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
MODEL_PRICES_PATH = Path(__file__).parent / "model_prices.json"
_JSON_OBJECT = re.compile(r"\{.*\}", re.S)
T = TypeVar("T", bound=BaseModel)


class UsageRecord(BaseModel):
    """Token usage of one LLM call."""

    node: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLMCallError(Exception):
    """The LLM could not produce a usable answer. Carries the tokens spent trying."""

    def __init__(self, message: str, usage: list[UsageRecord] | None = None) -> None:
        super().__init__(message)
        self.usage = usage or []


@dataclass(frozen=True)
class Provider:
    name: str  # "openrouter" or "openai"
    api_key: str
    base_url: str | None


def resolve_provider(env: dict[str, str] | None = None) -> Provider | None:
    """Pick the provider from the environment. None when no API key is configured."""
    env = dict(os.environ) if env is None else env
    if key := env.get("OPENROUTER_API_KEY", "").strip():
        return Provider("openrouter", key, OPENROUTER_BASE_URL)
    if key := env.get("OPENAI_API_KEY", "").strip():
        return Provider("openai", key, None)
    return None


def get_chat_model(settings: Settings, provider: Provider | None = None) -> BaseChatModel | None:
    """Build the chat model, or return None when no API key is available.

    Returning None (instead of raising) lets the agent still produce the deterministic
    part of the review: security findings and the cost estimate.
    """
    from langchain_openai import ChatOpenAI

    provider = provider or resolve_provider()
    if provider is None:
        return None
    model = settings.model
    if provider.name == "openai":
        model = model.removeprefix("openai/")  # OpenRouter ids carry a vendor prefix
    return ChatOpenAI(
        model=model,
        api_key=provider.api_key,
        base_url=provider.base_url,
        temperature=settings.temperature,
        seed=settings.seed,
        timeout=settings.llm_timeout_s,
        max_retries=settings.llm_max_retries,
    )


def call_json(
    llm: BaseChatModel | None, node: str, system: str, user: str, schema: type[T]
) -> tuple[T, list[UsageRecord]]:
    """Ask for a JSON object and validate it against `schema`."""
    if llm is None:
        raise LLMCallError("No LLM is configured (missing API key).")
    json_llm = llm.bind(response_format={"type": "json_object"})
    messages: list[BaseMessage] = [SystemMessage(content=system), HumanMessage(content=user)]
    usage: list[UsageRecord] = []
    for _attempt in range(2):
        try:
            reply = json_llm.invoke(messages)
        except Exception as exc:
            # Only the exception type is reported: messages can contain request details.
            raise LLMCallError(f"LLM call failed ({type(exc).__name__}).", usage) from exc
        usage.append(_usage_of(reply, node, llm))
        text = _text_of(reply)
        try:
            return schema.model_validate(_extract_json(text)), usage
        except (ValidationError, ValueError):
            messages += [
                reply,
                HumanMessage(
                    content="That reply was not valid JSON for the required schema. "
                    "Reply again with only the JSON object, nothing else."
                ),
            ]
    raise LLMCallError("The LLM did not return valid JSON after one retry.", usage)


def _extract_json(text: str) -> Any:
    match = _JSON_OBJECT.search(text)
    if not match:
        raise ValueError("no JSON object in reply")
    return json.loads(match.group(0))


def _text_of(reply: BaseMessage) -> str:
    content = reply.content
    if isinstance(content, str):
        return content
    parts = [part.get("text", "") if isinstance(part, dict) else str(part) for part in content]
    return "".join(parts)


def _usage_of(reply: BaseMessage, node: str, llm: BaseChatModel) -> UsageRecord:
    usage = getattr(reply, "usage_metadata", None) or {}
    return UsageRecord(
        node=node,
        model=model_name(llm),
        input_tokens=int(usage.get("input_tokens", 0)),
        output_tokens=int(usage.get("output_tokens", 0)),
    )


def model_name(llm: BaseChatModel | None) -> str:
    if llm is None:
        return "none"
    return str(getattr(llm, "model_name", None) or getattr(llm, "model", None) or "unknown")


# ------------------------------------------------------------------- token cost


def load_model_prices(path: Path = MODEL_PRICES_PATH) -> dict[str, dict[str, float]]:
    return json.loads(path.read_text(encoding="utf-8"))["usd_per_1m_tokens"]


def usage_cost_usd(
    usage: list[UsageRecord], prices: dict[str, dict[str, float]] | None = None
) -> float | None:
    """Cost of the recorded calls in USD, or None when a model's price is unknown."""
    prices = load_model_prices() if prices is None else prices
    total = 0.0
    for record in usage:
        price = prices.get(record.model) or prices.get(f"openai/{record.model}")
        if price is None:
            return None
        total += record.input_tokens * price["input"] / 1e6
        total += record.output_tokens * price["output"] / 1e6
    return round(total, 6)
