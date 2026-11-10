"""Node 8: write the summary and the recommendations, then assemble the report.

Uses the LLM for the summary and the cost/sizing/simplification recommendations. The
security findings and the cost estimate are added by code in `agent.report.build_report`.

Fallback when the LLM is unavailable: the report contains the deterministic results only
and says that the advisory part is missing.
"""

from __future__ import annotations

import json
from typing import Any

from agent.deps import Deps
from agent.llm import LLMCallError, UsageRecord, call_json, model_name
from agent.report import ReportDraft, build_report
from agent.state import ReviewState
from agent.summary import summarize_resources, wrap_data

FALLBACK_SUMMARY = (
    "The AI summary and recommendations are not available for this review. "
    "The security findings and the cost estimate below were produced by code and are complete."
)


def _payload(state: ReviewState) -> dict[str, Any]:
    cost = state.cost_estimate
    return {
        "resources": summarize_resources(state.resources),
        "cost": cost.model_dump(mode="json", include={"lines", "total_monthly_usd", "notes"})
        if cost
        else None,
        "security_findings": [
            {"rule_id": f.rule_id, "severity": f.severity.value, "resource": f.resource}
            for f in state.security_findings
        ],
        "documents": [
            {"id": doc.id, "title": doc.title, "text": doc.text} for doc in state.relevant_docs
        ],
        "project": state.constraints.model_dump(),
    }


def make_write_report(deps: Deps):
    def write_report(state: ReviewState) -> dict[str, Any]:
        system = deps.prompt("write_report")
        if deps.settings.extra_instructions.strip():
            system += (
                "\n\n## Additional instructions from the developer\n\n"
                + deps.settings.extra_instructions.strip()
            )
        new_usage: list[UsageRecord] = []
        errors: list[str] = []
        try:
            draft, new_usage = call_json(
                deps.llm,
                "write_report",
                system,
                wrap_data(json.dumps(_payload(state), indent=1)),
                ReportDraft,
            )
        except LLMCallError as exc:
            draft = ReportDraft(summary=FALLBACK_SUMMARY)
            new_usage = exc.usage
            errors.append(f"AI recommendations unavailable: {exc}")
        # Errors are added to a copy so they show up in this report's warnings.
        with_errors = state.model_copy(update={"errors": [*state.errors, *errors]})
        report = build_report(with_errors, draft, model_name(deps.llm), [*state.usage, *new_usage])
        return {"report": report, "usage": new_usage, "errors": errors}

    return write_report
