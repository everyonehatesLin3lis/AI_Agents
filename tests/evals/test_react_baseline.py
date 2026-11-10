"""The ReAct baseline: an LLM with function calling over the same tools as the graph.

The LLM is a scripted fake that issues tool calls. The tools (security rules, cost
estimator, Chroma search) are real.
"""

import json
from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from evals.dataset_loader import load_samples
from evals.react_baseline import run_react_review
from tools.models import Category

SAMPLES = {s.file: s for s in load_samples()}
SQL_OPEN = SAMPLES["vulnerable/sql_open.tf"]

Step = AIMessage | Callable[[list[BaseMessage]], AIMessage]


class ScriptedToolModel(BaseChatModel):
    """A chat model that plays a fixed script of tool calls and a final answer.

    A step is either a ready message or a function of the conversation so far, so a
    step can build its answer from what a tool returned.
    """

    script: list[Any] = []
    bound_tools: list[str] = []
    model_name: str = "fake-model"

    @property
    def _llm_type(self) -> str:
        return "scripted-tools"

    def bind_tools(self, tools: Any, **kwargs: Any) -> "ScriptedToolModel":
        self.bound_tools[:] = [getattr(t, "name", None) or t["name"] for t in tools]
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        step = self.script.pop(0)
        message = step(messages) if callable(step) else step
        message.usage_metadata = {"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
        return ChatResult(generations=[ChatGeneration(message=message)])


def call(tool: str, **args: Any) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": tool, "args": args, "id": f"call-{tool}"}])


def tool_result(messages: list[BaseMessage], tool: str) -> Any:
    message = next(m for m in messages if isinstance(m, ToolMessage) and m.name == tool)
    return json.loads(message.content)


def answer_repeating_security_findings(messages: list[BaseMessage]) -> AIMessage:
    findings = tool_result(messages, "check_security")
    return AIMessage(content=json.dumps({"summary": "One open database.", "findings": findings}))


def security_pairs(report) -> set[tuple[str, str]]:
    return {(f.resource, f.rule_id) for f in report.findings if f.category == Category.SECURITY}


def test_findings_returned_by_a_tool_call_reach_the_report(make_deps):
    model = ScriptedToolModel(
        script=[call("check_security"), answer_repeating_security_findings], bound_tools=[]
    )

    report = run_react_review(SQL_OPEN.terraform, make_deps(model))

    assert report.status == "ok"
    assert security_pairs(report) == {(e.resource, e.rule_id) for e in SQL_OPEN.expected_findings}
    assert set(model.bound_tools) == {"check_security", "estimate_cost", "search_gcp_docs"}


def test_a_model_that_obeys_injected_text_drops_the_findings_but_the_graph_keeps_them(
    make_deps, make_llm
):
    """What the baseline is for. The file tells the reviewer to report zero findings.
    A model that obeys can simply not call the security tool, and nothing stops it.
    The graph runs the rules in code, so the same obedient model changes nothing."""
    from agent.runner import run_review

    injected = SAMPLES["injection/comment_override.tf"]
    expected = {(e.resource, e.rule_id) for e in injected.expected_findings}
    safe = {"summary": "This configuration is safe.", "findings": []}
    obedient_react = ScriptedToolModel(script=[AIMessage(content=json.dumps(safe))])
    obedient_graph = make_llm(
        {"PLAN_RESEARCH": {"queries": []}, "WRITE_REPORT": {"summary": safe["summary"]}}
    )

    react_report = run_react_review(injected.terraform, make_deps(obedient_react))
    graph_report = run_review(injected.terraform, deps=make_deps(obedient_graph))

    assert security_pairs(react_report) == set()
    assert security_pairs(graph_report) == expected


def test_tool_results_and_usage_are_recorded_on_the_report(make_deps):
    import pytest

    model = ScriptedToolModel(
        script=[
            call("estimate_cost"),
            call("search_gcp_docs", query="cost of a regional standby", service="cloud_sql"),
            AIMessage(content=json.dumps({"summary": "Costed.", "findings": []})),
        ]
    )

    report = run_react_review(SQL_OPEN.terraform, make_deps(model))

    assert report.cost_estimate.total_monthly_usd == pytest.approx(231.25, abs=0.01)
    assert report.evidence and all(doc.service == "cloud_sql" for doc in report.evidence)
    assert report.usage.llm_calls == 3
    assert (report.usage.input_tokens, report.usage.output_tokens) == (300, 60)
    assert report.usage.calls_by_node["tool:estimate_cost"] == 1
    assert report.usage.calls_by_node["tool:search_gcp_docs"] == 1


def test_an_unusable_final_answer_gives_a_failed_report_not_an_exception(make_deps):
    model = ScriptedToolModel(script=[call("check_security"), AIMessage(content="I am done.")])

    report = run_react_review(SQL_OPEN.terraform, make_deps(model))

    assert report.status == "failed"
    assert report.findings == []
    assert report.usage.llm_calls == 2  # the tokens spent are still counted
    assert any("ReAct" in warning for warning in report.warnings)


def test_eval_loop_scores_the_react_baseline_with_the_same_metrics(make_deps):
    from evals.llm_eval import run_llm_eval, summarize

    model = ScriptedToolModel(script=[call("check_security"), answer_repeating_security_findings])

    records = run_llm_eval(
        models=["fake-model"],
        configs={"fake-model": ["react"]},
        runs=1,
        samples=[SQL_OPEN],
        deps_factory=lambda name, overrides: make_deps(model, **overrides),
        prices={"fake-model": {"input": 1.0, "output": 2.0}},
        progress=lambda line: None,
    )
    row = summarize(records)[0]

    assert records[0]["status"] == "ok"
    assert records[0]["tool_calls"] == {"check_security": 1}
    assert (row["config"], row["security_recall"], row["security_precision"]) == ("react", 1.0, 1.0)
    assert row["security_tool_skipped"] == 0
    assert row["llm_calls_mean"] == 2.0
