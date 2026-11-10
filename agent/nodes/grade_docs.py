"""Node 6: keep only the documents that are actually useful. Uses the LLM.

Why an LLM here: vector search returns the nearest passages, not necessarily relevant
ones. Grading stops the report from citing a passage that only shares keywords.

Fallback when the LLM is unavailable: keep everything that was retrieved.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from agent.deps import Deps
from agent.llm import LLMCallError, call_json
from agent.state import ReviewState
from agent.summary import summarize_resources, wrap_data


class Grades(BaseModel):
    relevant_ids: list[str] = Field(default_factory=list)


def make_grade_docs(deps: Deps):
    def grade_docs(state: ReviewState) -> dict[str, Any]:
        if not state.docs:
            return {}
        payload = {
            "resources": summarize_resources(state.resources),
            "queries": [query.query for query in state.queries],
            "documents": [
                {"id": doc.id, "title": doc.title, "text": doc.text} for doc in state.docs
            ],
        }
        try:
            grades, usage = call_json(
                deps.llm,
                "grade_docs",
                deps.prompt("grade_docs"),
                wrap_data(json.dumps(payload, indent=1)),
                Grades,
            )
        except LLMCallError as exc:
            return {
                "relevant_docs": [*state.relevant_docs, *state.docs],
                "errors": [f"Document grading skipped, all results kept: {exc}"],
                "usage": exc.usage,
                "stop_research": True,
            }
        wanted = set(grades.relevant_ids)
        kept = [doc for doc in state.docs if doc.id in wanted]
        return {"relevant_docs": [*state.relevant_docs, *kept], "usage": usage}

    return grade_docs
