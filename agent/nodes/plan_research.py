"""Node 4: decide what to look up in the documentation. Uses the LLM.

Why an LLM here: which topics are worth researching depends on judgment about the whole
configuration (what is expensive, what looks oversized, what the project prefers).

Fallback when the LLM is unavailable: one generic cost query per service, most expensive
service first. The review still gets documents, just less targeted ones.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from agent.deps import Deps
from agent.llm import LLMCallError, call_json
from agent.state import ResearchQuery, ReviewState
from agent.summary import summarize_resources, wrap_data
from tools.models import Service

SERVICE_LABELS = {
    Service.CLOUD_RUN: "Cloud Run",
    Service.COMPUTE: "Compute Engine virtual machines and disks",
    Service.CLOUD_SQL: "Cloud SQL",
    Service.CLOUD_STORAGE: "Cloud Storage",
    Service.GKE: "Google Kubernetes Engine",
}
VALID_SERVICES = {service.value for service in Service}


class ResearchPlan(BaseModel):
    queries: list[ResearchQuery] = Field(default_factory=list)


def clean_queries(queries: list[ResearchQuery], limit: int) -> list[ResearchQuery]:
    """Drop empty queries, unknown services and anything over the limit."""
    cleaned = []
    for query in queries:
        text = query.query.strip()[:200]
        if text:
            service = query.service if query.service in VALID_SERVICES else None
            cleaned.append(ResearchQuery(query=text, service=service))
    return cleaned[:limit]


def fallback_queries(state: ReviewState, limit: int) -> list[ResearchQuery]:
    lines = state.cost_estimate.lines if state.cost_estimate else []
    by_service: dict[Service, float] = {}
    for line in lines:
        by_service[line.service] = by_service.get(line.service, 0.0) + line.monthly_usd
    ranked = sorted(by_service, key=lambda service: by_service[service], reverse=True)
    return [
        ResearchQuery(query=f"how to reduce the cost of {SERVICE_LABELS[s]}", service=s.value)
        for s in ranked[:limit]
    ]


def make_plan_research(deps: Deps):
    def plan_research(state: ReviewState) -> dict[str, Any]:
        settings = deps.settings
        if not settings.use_rag or not any(r.supported for r in state.resources):
            return {"queries": []}
        payload = {
            "resources": summarize_resources(state.resources),
            "cost_lines": [
                line.model_dump(mode="json")
                for line in (state.cost_estimate.lines if state.cost_estimate else [])
            ],
            "security_rule_ids": sorted({f.rule_id for f in state.security_findings if f.rule_id}),
            "project": state.constraints.model_dump(),
        }
        try:
            plan, usage = call_json(
                deps.llm,
                "plan_research",
                deps.prompt("plan_research"),
                wrap_data(json.dumps(payload, indent=1)),
                ResearchPlan,
            )
        except LLMCallError as exc:
            return {
                "queries": fallback_queries(state, settings.max_queries),
                "errors": [f"Research planning used default queries: {exc}"],
                "usage": exc.usage,
                "stop_research": True,
            }
        return {"queries": clean_queries(plan.queries, settings.max_queries), "usage": usage}

    return plan_research
