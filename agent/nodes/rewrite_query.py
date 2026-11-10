"""Node 7: rewrite the queries when the search found too little. Uses the LLM.

This is the loop in the graph. It runs at most `max_rewrites` times (2 by default),
then the review continues with whatever was found. The counter lives in the state, and
the routing function in `graph.py` checks it, so the loop cannot run forever.
"""

from __future__ import annotations

import json
from typing import Any

from agent.deps import Deps
from agent.llm import LLMCallError, call_json
from agent.nodes.plan_research import ResearchPlan, clean_queries
from agent.state import ReviewState
from agent.summary import summarize_resources, wrap_data


def make_rewrite_query(deps: Deps):
    def rewrite_query(state: ReviewState) -> dict[str, Any]:
        count = state.rewrite_count + 1
        payload = {
            "resources": summarize_resources(state.resources),
            "previous_queries": [query.model_dump() for query in state.queries],
            "found_titles": [doc.title for doc in state.docs],
        }
        try:
            plan, usage = call_json(
                deps.llm,
                "rewrite_query",
                deps.prompt("rewrite_query"),
                wrap_data(json.dumps(payload, indent=1)),
                ResearchPlan,
            )
        except LLMCallError as exc:
            return {
                "rewrite_count": count,
                "errors": [f"Query rewrite failed: {exc}"],
                "usage": exc.usage,
                "stop_research": True,
            }
        queries = clean_queries(plan.queries, deps.settings.max_queries)
        if not queries:
            return {"rewrite_count": count, "usage": usage, "stop_research": True}
        return {"rewrite_count": count, "queries": queries, "usage": usage}

    return rewrite_query
