"""Assemble the final report and render it as Markdown.

`build_report` is where deterministic results and LLM output meet, so it is also where
the guarantees are enforced:

- Security findings are copied from the rule engine and checked afterwards
  (`verify_security_findings`). If one were missing or altered, the review fails loudly.
- LLM recommendations pass through `to_findings`, which drops anything about a resource
  that does not exist, only accepts a source that was actually retrieved, caps savings
  at the resource's own cost and removes links that do not point to Google Cloud docs.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from agent.llm import UsageRecord, usage_cost_usd
from agent.state import ReviewReport, ReviewState, UsageSummary
from memory.feedback_policy import apply_feedback
from tools.models import Category, CostEstimate, Doc, Finding, Severity

MAX_RECOMMENDATIONS = 6
MAX_SUMMARY_CHARS = 1200
SUGGESTION_PREFIX = "Suggestion (no documentation source): "
_URL = re.compile(r"https?://[^\s)\]>\"']+")
_ALLOWED_URL = re.compile(r"^https://(docs\.)?cloud\.google\.com/")


class Recommendation(BaseModel):
    """One recommendation as written by the LLM. The types limit what it can claim."""

    resource: str
    category: Literal["cost", "sizing", "simplification"]  # never "security"
    severity: Literal["medium", "low"] = "low"  # the LLM cannot raise a critical/high
    issue: str
    recommendation: str
    estimated_savings_usd: float | None = None
    doc_id: str | None = None


class ReportDraft(BaseModel):
    summary: str = ""
    recommendations: list[Recommendation] = Field(default_factory=list)


class SecurityIntegrityError(Exception):
    """A deterministic security finding is missing or changed in the final report."""


def strip_untrusted_urls(text: str) -> str:
    """Remove links that do not point to Google Cloud documentation."""
    return _URL.sub(
        lambda m: m.group(0) if _ALLOWED_URL.match(m.group(0)) else "[link removed]", text
    )


def to_findings(
    draft: ReportDraft, known_resources: set[str], docs: list[Doc], cost: CostEstimate | None
) -> list[Finding]:
    """Turn LLM recommendations into findings, enforcing the rules described above."""
    sources = {doc.id: doc.source_url for doc in docs}
    line_cost = {line.resource: line.monthly_usd for line in cost.lines} if cost else {}
    findings: list[Finding] = []
    for item in draft.recommendations[:MAX_RECOMMENDATIONS]:
        if item.resource not in known_resources:
            continue  # the LLM may not invent resources
        source_url = sources.get(item.doc_id or "")
        text = strip_untrusted_urls(item.recommendation)
        findings.append(
            Finding(
                severity=Severity(item.severity),
                resource=item.resource,
                issue=strip_untrusted_urls(item.issue),
                recommendation=text if source_url else SUGGESTION_PREFIX + text,
                estimated_savings=_cap_savings(
                    item.estimated_savings_usd, line_cost.get(item.resource)
                ),
                source_url=source_url,
                category=Category(item.category),
            )
        )
    return findings


def _cap_savings(savings: float | None, resource_cost: float | None) -> float | None:
    if savings is None or savings <= 0 or not resource_cost:
        return None
    return round(min(savings, resource_cost), 2)


def verify_security_findings(expected: list[Finding], final: list[Finding]) -> None:
    """Every deterministic security finding must be in the report, unchanged."""
    final_security = [f for f in final if f.category == Category.SECURITY]
    missing = [f for f in expected if f not in final_security]
    extra = [f for f in final_security if f not in expected]
    if missing or extra:
        raise SecurityIntegrityError(
            f"{len(missing)} security finding(s) missing or changed, {len(extra)} unexpected."
        )


def headline(findings: list[Finding], cost: CostEstimate | None) -> str:
    """One factual line computed from the findings. The LLM has no part in it."""
    security = [f for f in findings if f.category == Category.SECURITY]
    counts = {s: sum(1 for f in security if f.severity == s) for s in Severity}
    parts = [f"{count} {severity.value}" for severity, count in counts.items() if count]
    text = (
        f"{len(security)} security finding(s): {', '.join(parts)}."
        if security
        else "No security findings from the rule checks."
    )
    if cost is not None:
        text += f" Estimated cost: ${cost.total_monthly_usd:,.2f}/month."
    return text


def summarize_usage(usage: list[UsageRecord]) -> UsageSummary:
    return UsageSummary(
        llm_calls=len(usage),
        input_tokens=sum(record.input_tokens for record in usage),
        output_tokens=sum(record.output_tokens for record in usage),
        cost_usd=usage_cost_usd(usage) if usage else 0.0,
        calls_by_node={
            node: sum(1 for record in usage if record.node == node)
            for node in dict.fromkeys(record.node for record in usage)
        },
    )


def build_report(
    state: ReviewState, draft: ReportDraft, model: str, usage: list[UsageRecord]
) -> ReviewReport:
    """Combine deterministic results, LLM recommendations and past feedback."""
    supported = [resource for resource in state.resources if resource.supported]
    recommendations = to_findings(
        draft, {r.address for r in supported}, state.relevant_docs, state.cost_estimate
    )
    findings = apply_feedback(
        [*state.security_findings, *state.cost_findings, *recommendations], state.past_feedback
    )
    verify_security_findings(state.security_findings, findings)
    return ReviewReport(
        review_id=state.review_id,
        project_id=state.project_id,
        model=model,
        headline=headline(findings, state.cost_estimate),
        summary=strip_untrusted_urls(draft.summary)[:MAX_SUMMARY_CHARS],
        findings=findings,
        cost_estimate=state.cost_estimate,
        resources_reviewed=len(supported),
        unsupported_resources=[r.address for r in state.resources if not r.supported],
        warnings=_warnings(state),
        sources=list(dict.fromkeys(f.source_url for f in findings if f.source_url)),
        evidence=state.relevant_docs,
        usage=summarize_usage(usage),
    )


def _warnings(state: ReviewState) -> list[str]:
    warnings = list(state.errors)
    cost = state.cost_estimate
    if cost is not None and cost.prices_may_be_outdated:
        warnings.append("Prices may be outdated: the static price table was used.")
    unsupported = [r.address for r in state.resources if not r.supported]
    if unsupported:
        warnings.append(
            f"{len(unsupported)} resource(s) are of an unsupported type and were not reviewed."
        )
    return list(dict.fromkeys(warnings))


def failed_report(state: ReviewState, message: str) -> ReviewReport:
    return ReviewReport(
        review_id=state.review_id,
        project_id=state.project_id,
        status="failed",
        headline="The review could not be completed.",
        summary=message,
        warnings=[message],
    )


# ------------------------------------------------------------------- rendering


def render_markdown(report: ReviewReport) -> str:
    """Human-readable report. Used by the MCP tool and the download button in the UI."""
    lines = ["# GCP infrastructure review", "", f"**{report.headline}**", ""]
    if report.summary:
        lines += [report.summary, ""]
    for warning in report.warnings:
        lines.append(f"> Warning: {warning}")
    if report.warnings:
        lines.append("")
    lines += _findings_section("Security findings", report.findings, security=True)
    lines += _findings_section("Cost and sizing recommendations", report.findings, security=False)
    lines += _cost_section(report.cost_estimate)
    if report.unsupported_resources:
        lines += ["## Not reviewed (unsupported resource types)", ""]
        lines += [f"- `{address}`" for address in report.unsupported_resources] + [""]
    usage = report.usage
    cost = "n/a" if usage.cost_usd is None else f"${usage.cost_usd:.4f}"
    lines.append(
        f"_Model: {report.model}. LLM calls: {usage.llm_calls}. Tokens: {usage.input_tokens} in "
        f"/ {usage.output_tokens} out. LLM cost: {cost}._"
    )
    return "\n".join(lines)


def _findings_section(title: str, findings: list[Finding], *, security: bool) -> list[str]:
    selected = [f for f in findings if (f.category == Category.SECURITY) == security]
    if not selected:
        return []
    lines = [f"## {title}", ""]
    for finding in selected:
        tag = f"{finding.rule_id} " if finding.rule_id else ""
        low = " (deprioritized by your earlier feedback)" if finding.deprioritized else ""
        lines.append(f"### [{finding.severity.value.upper()}] {tag}`{finding.resource}`{low}")
        lines.append(f"- **Issue:** {finding.issue}")
        if finding.terraform_fields:
            shown = "; ".join(f"`{field}`" for field in finding.terraform_fields)
            lines.append(f"- **In your Terraform:** {shown}")
        lines.append(f"- **Recommendation:** {finding.recommendation}")
        if finding.estimated_savings:
            lines.append(f"- **Estimated savings:** ${finding.estimated_savings:,.2f}/month")
        if finding.source_url:
            lines.append(f"- **Source:** {finding.source_url}")
        lines.append("")
    return lines


def _cost_section(cost: CostEstimate | None) -> list[str]:
    if cost is None:
        return []
    lines = [
        "## Cost estimate",
        "",
        f"Total: **${cost.total_monthly_usd:,.2f} per month** "
        f"(price source: {cost.price_source}, "
        f"priced in: {', '.join(cost.regions_used) or cost.default_region})",
        "",
        "| Resource | USD/month | Assumptions |",
        "|---|---:|---|",
    ]
    for line in cost.lines:
        amount = f"{line.monthly_usd:,.2f}" if line.priced else "not priced"
        lines.append(f"| `{line.resource}` | {amount} | {' '.join(line.assumptions)} |")
    lines.append("")
    lines += [f"- {note}" for note in cost.notes]
    return lines + [""]
