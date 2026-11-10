"""A ReAct baseline for the research comparison. It is not used by the UI or the MCP tool.

The same job as the graph agent, built the other way round: one LLM in a loop with
function calling. The model is given the Terraform file and three tools (the same
security rules, cost estimator and documentation search the graph uses), decides which
to call and when, and writes the whole report itself, security findings included.

Nothing here checks the model's answer against the rule output. That is the point of
the baseline: it shows what the graph's fixed order and integrity check are worth.
`run_react_review` returns the same `ReviewReport` as the graph, so the same metrics
apply to both.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import BaseTool, tool
from pydantic import BaseModel, Field

from agent.deps import Deps
from agent.llm import LLMCallError, UsageRecord, _extract_json, _text_of, model_name
from agent.report import summarize_usage
from agent.state import ReviewReport
from tools.cost_estimator import estimate_cost
from tools.models import Category, CostEstimate, Doc, Finding, Severity
from tools.security_rules import check_security
from tools.tf_parser import parse_terraform, validate_terraform_input

PROMPT = (Path(__file__).parent / "prompts" / "react_baseline.md").read_text(encoding="utf-8")
MAX_STEPS = 16  # LangGraph recursion limit: bounds the loop, and so the cost
NODE = "react"


class ReactFinding(BaseModel):
    """A finding as the model wrote it. Unlike the graph's `Recommendation`, any
    category and any severity is accepted: the baseline trusts the model."""

    severity: Severity
    resource: str
    issue: str
    recommendation: str
    category: Category = Category.SECURITY
    rule_id: str | None = None
    source_url: str | None = None


class ReactAnswer(BaseModel):
    summary: str = ""
    findings: list[ReactFinding] = Field(default_factory=list)


class _ToolSession:
    """The tools for one review, and a record of what they returned."""

    def __init__(self, terraform: str, deps: Deps) -> None:
        self._terraform = terraform
        self._deps = deps
        self.cost: CostEstimate | None = None
        self.docs: dict[str, Doc] = {}
        self.calls: dict[str, int] = {}

    def _count(self, name: str) -> None:
        self.calls[name] = self.calls.get(name, 0) + 1

    def tools(self) -> list[BaseTool]:
        @tool("check_security")
        def security_tool() -> str:
            """Run the fixed security rules on the Terraform file. Returns a JSON list of
            findings, each with rule_id, severity, resource, issue, recommendation and
            source_url."""
            self._count("check_security")
            findings = check_security(parse_terraform(self._terraform))
            return json.dumps([f.model_dump(mode="json") for f in findings])

        @tool("estimate_cost")
        def cost_tool() -> str:
            """Estimate the monthly cost in USD of every resource in the Terraform file.
            Returns JSON with one line per resource and the assumptions made."""
            self._count("estimate_cost")
            settings = self._deps.settings
            self.cost = estimate_cost(
                parse_terraform(self._terraform),
                settings.default_region,
                self._deps.prices(),
                settings.assumed_storage_gb,
            )
            return self.cost.model_dump_json()

        @tool("search_gcp_docs")
        def search_tool(query: str, service: str | None = None) -> str:
            """Search Google Cloud documentation notes. `query` is one short question.
            `service` is one of cloud_run, compute, cloud_sql, cloud_storage, gke, or
            null for all. Returns JSON passages with title, text and source_url."""
            self._count("search_gcp_docs")
            docs = self._deps.search(query, service, self._deps.settings.retrieval_k)
            self.docs.update({doc.id: doc for doc in docs})
            return json.dumps([doc.model_dump(mode="json", exclude={"score"}) for doc in docs])

        return [security_tool, cost_tool, search_tool]


def run_react_review(
    terraform: str, deps: Deps, project_id: str = "react-baseline"
) -> ReviewReport:
    """Review Terraform with the ReAct baseline. Raises `TerraformInputError` on bad input.

    A loop that fails or an answer that is not a valid report gives a report with status
    "failed" and a warning, so an eval run records it and goes on.
    """
    validate_terraform_input(terraform)
    if deps.llm is None:
        raise LLMCallError("No LLM is configured (missing API key).")
    session = _ToolSession(terraform, deps)
    agent = create_agent(deps.llm, session.tools(), system_prompt=PROMPT)
    start = deps.clock()
    messages: list[Any] = []
    answer, problem = None, None
    try:
        result = agent.invoke(
            {"messages": [HumanMessage(content=terraform)]}, {"recursion_limit": MAX_STEPS}
        )
        messages = result["messages"]
        answer = ReactAnswer.model_validate(_extract_json(_text_of(messages[-1])))
    except ValueError:  # includes pydantic's ValidationError
        problem = "The ReAct baseline did not return a valid JSON report."
    except Exception as exc:  # provider error, or the step limit was reached
        problem = f"The ReAct loop failed ({type(exc).__name__})."
    return _report(answer, problem, messages, session, deps, project_id, deps.clock() - start)


def _report(
    answer: ReactAnswer | None,
    problem: str | None,
    messages: list[Any],
    session: _ToolSession,
    deps: Deps,
    project_id: str,
    seconds: float,
) -> ReviewReport:
    model = model_name(deps.llm)
    usage = [
        UsageRecord(
            node=NODE,
            model=model,
            input_tokens=int((m.usage_metadata or {}).get("input_tokens", 0)),
            output_tokens=int((m.usage_metadata or {}).get("output_tokens", 0)),
        )
        for m in messages
        if isinstance(m, AIMessage)
    ]
    findings = [Finding(**item.model_dump()) for item in answer.findings] if answer else []
    summary = summarize_usage(usage)
    summary.calls_by_node |= {f"tool:{name}": count for name, count in session.calls.items()}
    return ReviewReport(
        review_id=uuid.uuid4().hex[:12],
        project_id=project_id,
        status="failed" if problem else "ok",
        model=model,
        headline=f"{len(findings)} finding(s) reported by the ReAct baseline.",
        summary=answer.summary if answer else "",
        warnings=[problem] if problem else [],
        findings=findings,
        cost_estimate=session.cost,
        sources=list(dict.fromkeys(f.source_url for f in findings if f.source_url)),
        evidence=list(session.docs.values()),
        usage=summary,
        timings={NODE: round(seconds, 4), "total": round(seconds, 4)},
    )
