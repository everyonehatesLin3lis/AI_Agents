"""Node 10: store the feedback and the finished review in long-term memory.

Feedback is stored as given, including feedback on security findings (useful as an audit
trail). Whether it has any effect is decided later by `memory.feedback_policy`, which
ignores it for security findings.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from agent.deps import Deps
from agent.state import ReviewState


def make_save_feedback(deps: Deps):
    def save_feedback(state: ReviewState) -> dict[str, Any]:
        if state.report is None:
            return {}
        try:
            if state.new_feedback:
                deps.store.add_feedback(state.project_id, state.review_id, state.new_feedback)
            deps.store.save_review(
                state.review_id, state.project_id, state.report.model_dump(mode="json")
            )
        except sqlite3.Error as exc:
            return {"errors": [f"Could not save to memory ({type(exc).__name__})."]}
        return {}

    return save_feedback
