"""Long-term memory in one SQLite file.

Three tables:

- `constraints`: what we know about a project (budget, region, preferences). Loaded into
  the graph state at the start of every review.
- `feedback`: what the user said about past findings. Used to lower the priority of cost
  and sizing suggestions the user has already dismissed (see `feedback_policy.py`).
- `reviews`: one row per finished review, for history and for the token/cost totals.

SQLite is enough here: one user, one machine, a few rows per review, no server to run.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

DEFAULT_DB_PATH = Path("data") / "memory.sqlite"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS constraints (
    project_id TEXT PRIMARY KEY,
    data       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id  TEXT NOT NULL,
    review_id   TEXT NOT NULL,
    finding_key TEXT NOT NULL,
    category    TEXT NOT NULL,
    action      TEXT NOT NULL,
    comment     TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
    review_id  TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    created_at TEXT NOT NULL,
    report     TEXT NOT NULL
);
"""


class ProjectConstraints(BaseModel):
    """Per-project facts the reviewer should take into account."""

    budget_monthly_usd: float | None = None
    region: str | None = None
    preferences: list[str] = Field(default_factory=list)  # free text, e.g. "prefer serverless"


class FeedbackAction(StrEnum):
    HELPFUL = "helpful"
    DISMISS = "dismiss"


class FeedbackItem(BaseModel):
    finding_key: str
    category: str
    action: FeedbackAction
    comment: str = ""


class StoredReview(BaseModel):
    review_id: str
    project_id: str
    created_at: str
    report: dict


class MemoryStore:
    """Small wrapper around SQLite. A new connection per call keeps it thread-safe."""

    def __init__(self, path: Path | str = DEFAULT_DB_PATH) -> None:
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            connection.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path, timeout=10)

    # ------------------------------------------------------------- constraints

    def get_constraints(self, project_id: str) -> ProjectConstraints:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT data FROM constraints WHERE project_id = ?", (project_id,)
            ).fetchone()
        return ProjectConstraints(**json.loads(row[0])) if row else ProjectConstraints()

    def save_constraints(self, project_id: str, constraints: ProjectConstraints) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT INTO constraints (project_id, data) VALUES (?, ?) "
                "ON CONFLICT(project_id) DO UPDATE SET data = excluded.data",
                (project_id, constraints.model_dump_json()),
            )

    # ---------------------------------------------------------------- feedback

    def add_feedback(self, project_id: str, review_id: str, items: list[FeedbackItem]) -> None:
        now = datetime.now(UTC).isoformat()
        rows = [
            (project_id, review_id, item.finding_key, item.category, item.action.value,
             item.comment, now)
            for item in items
        ]  # fmt: skip
        with closing(self._connect()) as connection, connection:
            connection.executemany(
                "INSERT INTO feedback (project_id, review_id, finding_key, category, action, "
                "comment, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                rows,
            )

    def get_feedback(self, project_id: str) -> list[FeedbackItem]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT finding_key, category, action, comment FROM feedback "
                "WHERE project_id = ? ORDER BY id",
                (project_id,),
            ).fetchall()
        return [
            FeedbackItem(finding_key=key, category=category, action=action, comment=comment)
            for key, category, action, comment in rows
        ]

    # ----------------------------------------------------------------- reviews

    def save_review(self, review_id: str, project_id: str, report: dict) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute(
                "INSERT OR REPLACE INTO reviews (review_id, project_id, created_at, report) "
                "VALUES (?, ?, ?, ?)",
                (review_id, project_id, datetime.now(UTC).isoformat(), json.dumps(report)),
            )

    def list_reviews(self, project_id: str, limit: int = 20) -> list[StoredReview]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT review_id, project_id, created_at, report FROM reviews "
                "WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
                (project_id, limit),
            ).fetchall()
        return [
            StoredReview(review_id=r, project_id=p, created_at=c, report=json.loads(report))
            for r, p, c, report in rows
        ]
