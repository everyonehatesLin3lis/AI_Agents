"""Node 3: estimate the monthly cost. Pure code, no LLM.

Uses long-term memory twice: the project's region is the default region for pricing,
and the project's budget turns into a finding when the estimate is above it.
"""

from __future__ import annotations

from typing import Any

from agent.deps import Deps
from agent.state import ReviewState
from tools.cost_estimator import estimate_cost
from tools.models import Category, CostEstimate, Finding, Severity

BUDGET_RULE_ID = "COST-BUDGET"
WHOLE_CONFIGURATION = "(whole configuration)"


def make_cost_estimate(deps: Deps):
    def cost_estimate(state: ReviewState) -> dict[str, Any]:
        region = state.constraints.region or deps.settings.default_region
        prices = deps.prices()
        try:
            estimate = estimate_cost(
                state.resources, region, prices, deps.settings.assumed_storage_gb
            )
        except Exception as exc:  # a pricing bug must not hide the security findings
            return {"errors": [f"Cost estimate failed ({type(exc).__name__})."]}
        errors = (
            [f"Billing API not used: {prices.fallback_reason}"] if prices.fallback_reason else []
        )
        budget = state.constraints.budget_monthly_usd
        return {
            "cost_estimate": estimate,
            "cost_findings": _budget_findings(estimate, budget),
            "errors": errors,
        }

    return cost_estimate


def _budget_findings(estimate: CostEstimate, budget: float | None) -> list[Finding]:
    if budget is None or estimate.total_monthly_usd <= budget:
        return []
    over = estimate.total_monthly_usd - budget
    largest = max(estimate.lines, key=lambda line: line.monthly_usd)
    return [
        Finding(
            severity=Severity.MEDIUM,
            resource=WHOLE_CONFIGURATION,
            issue=f"Estimated cost ${estimate.total_monthly_usd:,.2f}/month is "
            f"${over:,.2f} above the project budget of ${budget:,.2f}.",
            recommendation=f"Start with the largest line: {largest.resource} "
            f"(${largest.monthly_usd:,.2f}/month).",
            rule_id=BUDGET_RULE_ID,
            category=Category.COST,
        )
    ]
