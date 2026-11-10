"""The review graph.

    parse -> security_check -> cost_estimate -> plan_research
          -> retrieve -> grade_docs -> (rewrite_query, at most 2 times) -> write_report
          -> human_review (interrupt) -> save_feedback

The three routing functions below are the only places where the path is decided, and
each one is a plain function of the state, so the control flow can be read and tested
without running an LLM.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from agent.deps import Deps
from agent.nodes.cost_estimate import make_cost_estimate
from agent.nodes.grade_docs import make_grade_docs
from agent.nodes.human_review import make_human_review
from agent.nodes.parse import make_parse
from agent.nodes.plan_research import make_plan_research
from agent.nodes.retrieve import make_retrieve
from agent.nodes.rewrite_query import make_rewrite_query
from agent.nodes.save_feedback import make_save_feedback
from agent.nodes.security_check import make_security_check
from agent.nodes.write_report import make_write_report
from agent.state import ReviewState

DETERMINISTIC_NODES = ("parse", "security_check", "cost_estimate", "retrieve")
LLM_NODES = ("plan_research", "grade_docs", "rewrite_query", "write_report")

Node = Callable[[ReviewState], dict[str, Any]]


def timed(name: str, node: Node, clock: Callable[[], float]) -> Node:
    """Wrap a node so the time it took is recorded in `state.timings[name]`."""

    def wrapper(state: ReviewState) -> dict[str, Any]:
        start = clock()
        update = dict(node(state))
        update["timings"] = {name: clock() - start}
        return update

    wrapper.__name__ = name
    return wrapper


def after_parse(state: ReviewState) -> str:
    return END if state.parse_failed else "security_check"


def after_plan(state: ReviewState) -> str:
    return "retrieve" if state.queries else "write_report"


def make_after_grade(min_relevant_docs: int, max_rewrites: int) -> Callable[[ReviewState], str]:
    def after_grade(state: ReviewState) -> str:
        enough = len(state.relevant_docs) >= min_relevant_docs
        can_retry = state.rewrite_count < max_rewrites and not state.stop_research
        return "write_report" if enough or not can_retry else "rewrite_query"

    return after_grade


def after_rewrite(state: ReviewState) -> str:
    return "write_report" if state.stop_research else "retrieve"


def build_graph(deps: Deps, checkpointer: BaseCheckpointSaver | None = None):
    """Compile the graph. A checkpointer is needed only for interactive reviews."""
    nodes: dict[str, Node] = {
        "parse": make_parse(deps),
        "security_check": make_security_check(deps),
        "cost_estimate": make_cost_estimate(deps),
        "plan_research": make_plan_research(deps),
        "retrieve": make_retrieve(deps),
        "grade_docs": make_grade_docs(deps),
        "rewrite_query": make_rewrite_query(deps),
        "write_report": make_write_report(deps),
        "human_review": make_human_review(deps),
        "save_feedback": make_save_feedback(deps),
    }
    graph = StateGraph(ReviewState)
    for name, node in nodes.items():
        # human_review is not timed: its "duration" is how long the person takes.
        graph.add_node(name, node if name == "human_review" else timed(name, node, deps.clock))

    settings = deps.settings
    graph.add_edge(START, "parse")
    graph.add_conditional_edges("parse", after_parse, ["security_check", END])
    graph.add_edge("security_check", "cost_estimate")
    graph.add_edge("cost_estimate", "plan_research")
    graph.add_conditional_edges("plan_research", after_plan, ["retrieve", "write_report"])
    graph.add_edge("retrieve", "grade_docs")
    graph.add_conditional_edges(
        "grade_docs",
        make_after_grade(settings.min_relevant_docs, settings.max_rewrites),
        ["rewrite_query", "write_report"],
    )
    graph.add_conditional_edges("rewrite_query", after_rewrite, ["retrieve", "write_report"])
    graph.add_edge("write_report", "human_review")
    graph.add_edge("human_review", "save_feedback")
    graph.add_edge("save_feedback", END)
    return graph.compile(checkpointer=checkpointer)
