"""The HTTP API: a thin adapter over the review service, used by the Node.js UI.

These tests check the mapping to routes, JSON and status codes. What a review contains
is tested at the service and the graph.
"""

import json

import pytest
from fastapi.testclient import TestClient

from agent.service import ReviewService
from api.server import create_app
from evals.dataset_loader import load_samples


@pytest.fixture
def make_client(make_deps):
    def _make(llm=None) -> TestClient:
        service = ReviewService(
            lambda settings: make_deps(llm, **settings.model_dump(exclude={"data_dir"}))
        )
        return TestClient(create_app(service))

    return _make


def test_capabilities_are_served_as_json(make_client):
    response = make_client().get("/api/capabilities")

    assert response.status_code == 200
    body = response.json()
    assert body["services"] == ["cloud_run", "compute", "cloud_sql", "cloud_storage", "gke"]
    assert body["max_input_kb"] == 200
    assert body["llm_configured"] is False


SQL_OPEN = next(s for s in load_samples() if s.file == "vulnerable/sql_open.tf")
WRITER = {"PLAN_RESEARCH": {"queries": []}, "WRITE_REPORT": {"summary": "One open database."}}


def _events(response) -> list[dict]:
    return [json.loads(line) for line in response.text.splitlines() if line.strip()]


def test_a_review_is_streamed_as_one_json_event_per_line(make_client, make_llm):
    client = make_client(make_llm(WRITER))

    response = client.post("/api/reviews", json={"terraform": SQL_OPEN.terraform})

    events = _events(response)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert [e["step"] for e in events[:3]] == ["parse", "security_check", "cost_estimate"]
    assert events[-1]["type"] == "report"
    assert events[-1]["waiting_for_feedback"] is True
    assert events[-1]["report"]["headline"].startswith("5 security finding(s)")


def test_rejected_input_is_an_event_with_a_message_not_a_server_error(make_client):
    response = make_client().post("/api/reviews", json={"terraform": 'print("hello")'})

    assert response.status_code == 200
    assert [e["type"] for e in _events(response)] == ["rejected"]


def test_a_malformed_request_is_refused_before_any_review_runs(make_client):
    client = make_client()

    assert client.post("/api/reviews", json={}).status_code == 422
    bad_project = {"terraform": SQL_OPEN.terraform, "project_id": "../etc"}
    assert client.post("/api/reviews", json=bad_project).status_code == 422


def test_feedback_finishes_a_review_and_maps_the_outcome_to_a_status(make_client, make_llm):
    client = make_client(make_llm(WRITER))
    review_id = _events(client.post("/api/reviews", json={"terraform": SQL_OPEN.terraform}))[-1][
        "report"
    ]["review_id"]

    unknown = client.post("/api/reviews/no-such-review/feedback", json={"feedback": []})
    first = client.post(f"/api/reviews/{review_id}/feedback", json={"feedback": []})
    again = client.post(f"/api/reviews/{review_id}/feedback", json={"feedback": []})

    assert (unknown.status_code, first.status_code, again.status_code) == (404, 200, 409)
    assert first.json() == {"status": "ok", "saved": 0, "ignored": 0}


def test_project_memory_can_be_read_and_saved(make_client):
    client = make_client()

    empty = client.get("/api/projects/shop/memory").json()
    saved = client.put(
        "/api/projects/shop/memory",
        json={"budget_monthly_usd": 100, "region": "europe-west1", "preferences": ["serverless"]},
    )

    assert empty == {"budget_monthly_usd": None, "region": None, "preferences": []}
    assert saved.status_code == 200
    assert client.get("/api/projects/shop/memory").json()["region"] == "europe-west1"


def test_samples_are_listed_and_served_and_unknown_names_are_not_found(make_client):
    client = make_client()

    assert "mixed/web_stack.tf" in client.get("/api/samples").json()["samples"]
    assert (
        "google_compute_instance"
        in client.get("/api/samples/mixed/web_stack.tf").json()["terraform"]
    )
    assert client.get("/api/samples/expected.json").status_code == 404
