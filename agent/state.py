"""The state that flows through the graph, and the report that comes out of it.

Each node reads the state and returns only the fields it changed. Three fields use a
*reducer* so that updates from different nodes are combined instead of overwritten:
`errors` and `usage` are appended to, and `timings` adds up (a node that runs twice in
the rewrite loop reports its total time).
"""

from __future__ import annotations

import operator
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from agent.llm import UsageRecord
from memory.store import FeedbackItem, ProjectConstraints
from tools.models import CostEstimate, Doc, Finding, Resource


def add_timings(left: dict[str, float], right: dict[str, float]) -> dict[str, float]:
    merged = dict(left)
    for name, seconds in right.items():
        merged[name] = round(merged.get(name, 0.0) + seconds, 4)
    return merged


class ResearchQuery(BaseModel):
    query: str
    service: str | None = None


class UsageSummary(BaseModel):
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None  # None = the model's price is not known
    calls_by_node: dict[str, int] = Field(default_factory=dict)


class ReviewReport(BaseModel):
    """The result of a review. This is what the UI shows and what the MCP tool returns."""

    review_id: str
    project_id: str
    status: Literal["ok", "failed"] = "ok"
    model: str = "none"
    headline: str = ""  # written by code from the findings, never by the LLM
    summary: str = ""  # written by the LLM (or a fallback text)
    findings: list[Finding] = Field(default_factory=list)
    cost_estimate: CostEstimate | None = None
    resources_reviewed: int = 0
    unsupported_resources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    evidence: list[Doc] = Field(default_factory=list)  # documents the LLM was given
    usage: UsageSummary = Field(default_factory=UsageSummary)
    timings: dict[str, float] = Field(default_factory=dict)


class ReviewState(BaseModel):
    # Input
    terraform: str
    project_id: str = "default"
    review_id: str
    interactive: bool = False  # True = pause at human_review and wait for feedback

    # Long-term memory, loaded before the graph starts
    constraints: ProjectConstraints = Field(default_factory=ProjectConstraints)
    past_feedback: list[FeedbackItem] = Field(default_factory=list)

    # Deterministic results
    resources: list[Resource] = Field(default_factory=list)
    parse_failed: bool = False
    security_findings: list[Finding] = Field(default_factory=list)
    cost_estimate: CostEstimate | None = None
    cost_findings: list[Finding] = Field(default_factory=list)

    # Research loop
    queries: list[ResearchQuery] = Field(default_factory=list)
    docs: list[Doc] = Field(default_factory=list)
    relevant_docs: list[Doc] = Field(default_factory=list)
    rewrite_count: int = 0
    stop_research: bool = False  # set when a step failed and looping would not help

    # Output
    report: ReviewReport | None = None
    new_feedback: list[FeedbackItem] = Field(default_factory=list)

    # Bookkeeping (reducers combine updates from all nodes)
    errors: Annotated[list[str], operator.add] = Field(default_factory=list)
    usage: Annotated[list[UsageRecord], operator.add] = Field(default_factory=list)
    timings: Annotated[dict[str, float], add_timings] = Field(default_factory=dict)
