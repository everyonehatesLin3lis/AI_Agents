"""Node 9: pause and let a person react to the report (human in the loop).

`interrupt()` stops the graph and saves its state in the checkpointer. The UI shows the
report, collects feedback, and resumes the graph with that feedback. When the review is
not interactive (MCP tool, evals), the node does nothing.
"""

from __future__ import annotations

from typing import Any

from langgraph.types import interrupt
from pydantic import ValidationError

from agent.deps import Deps
from agent.state import ReviewState
from memory.store import FeedbackItem


def parse_feedback(raw: Any) -> list[FeedbackItem]:
    """Validate what came back from the UI. Anything malformed is ignored."""
    items: list[FeedbackItem] = []
    for entry in raw if isinstance(raw, list) else []:
        try:
            items.append(FeedbackItem.model_validate(entry))
        except ValidationError:
            continue
    return items


def make_human_review(deps: Deps):
    def human_review(state: ReviewState) -> dict[str, Any]:
        if not state.interactive or state.report is None:
            return {}
        answer = interrupt({"review_id": state.review_id, "report": state.report.model_dump()})
        return {"new_feedback": parse_feedback(answer)}

    return human_review
