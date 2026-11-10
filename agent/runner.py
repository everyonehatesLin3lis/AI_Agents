"""Entry points for running a review.

- `run_review` runs the whole graph in one go. Used by the MCP tool and the evals.
- `ReviewSession` runs it in two steps for the UI: `start` stops at the human review
  interrupt and returns the report, `finish` resumes the graph with the feedback.

Both validate the input before the graph starts, load the project's long-term memory
into the initial state, and attach the timings to the report.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

from dotenv import load_dotenv
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from agent.deps import Deps, default_deps
from agent.graph import build_graph
from agent.report import summarize_usage
from agent.state import ReviewReport, ReviewState
from memory.store import FeedbackItem
from tools.tf_parser import validate_terraform_input

load_dotenv()  # reads .env so API keys and LangSmith tracing settings are available


class ReviewNotPausedError(RuntimeError):
    """`finish` was called for a review that is not waiting for feedback."""


def _initial_state(terraform: str, project_id: str, deps: Deps, interactive: bool) -> ReviewState:
    return ReviewState(
        terraform=terraform,
        project_id=project_id,
        review_id=uuid.uuid4().hex[:12],
        interactive=interactive,
        constraints=deps.store.get_constraints(project_id),
        past_feedback=deps.store.get_feedback(project_id),
    )


def _finalize(values: dict[str, Any], total_seconds: float) -> ReviewReport:
    """Take the report out of the final state and attach timings and total usage."""
    report: ReviewReport = values["report"]
    timings = {**values.get("timings", {}), "total": round(total_seconds, 4)}
    return report.model_copy(
        update={"timings": timings, "usage": summarize_usage(values.get("usage", []))}
    )


def run_review(
    terraform: str, project_id: str = "default", *, deps: Deps | None = None
) -> ReviewReport:
    """Review Terraform and return the report. Raises `TerraformInputError` on bad input."""
    validate_terraform_input(terraform)
    deps = deps or default_deps()
    graph = build_graph(deps)
    start = deps.clock()
    values = graph.invoke(_initial_state(terraform, project_id, deps, interactive=False))
    return _finalize(values, deps.clock() - start)


class ReviewSession:
    """A review that pauses for human feedback. One session can run many reviews."""

    def __init__(self, deps: Deps | None = None) -> None:
        self.deps = deps or default_deps()
        self._graph = build_graph(self.deps, checkpointer=InMemorySaver())

    @staticmethod
    def _config(review_id: str) -> dict[str, Any]:
        return {"configurable": {"thread_id": review_id}}

    def start(self, terraform: str, project_id: str = "default") -> ReviewReport:
        """Run until the human review step and return the report to show."""
        report = None
        for item in self.start_steps(terraform, project_id):
            report = item
        assert isinstance(report, ReviewReport)
        return report

    def start_steps(
        self, terraform: str, project_id: str = "default"
    ) -> Iterator[str | ReviewReport]:
        """Like `start`, but yields the name of each graph node as it finishes, and the
        report last. A front end uses the names to show progress while it waits."""
        validate_terraform_input(terraform)
        state = _initial_state(terraform, project_id, self.deps, interactive=True)
        config = self._config(state.review_id)
        start = self.deps.clock()
        for update in self._graph.stream(state, config, stream_mode="updates"):
            for node in update:
                if not node.startswith("__"):  # "__interrupt__" is the pause, not a step
                    yield node
        values = self._graph.get_state(config).values
        yield _finalize(values, self.deps.clock() - start)

    def is_waiting(self, review_id: str) -> bool:
        return bool(self._graph.get_state(self._config(review_id)).next)

    def finish(self, review_id: str, feedback: list[FeedbackItem]) -> None:
        """Resume a paused review with the user's feedback and save it."""
        if not self.is_waiting(review_id):
            raise ReviewNotPausedError(f"Review {review_id} is not waiting for feedback.")
        answer = [item.model_dump(mode="json") for item in feedback]
        self._graph.invoke(Command(resume=answer), self._config(review_id))
