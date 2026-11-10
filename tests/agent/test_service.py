"""The review service: the one interface every front end uses (HTTP API, MCP).

The LLM is faked. The graph, tools, Chroma collection and SQLite store are real.
"""

import pytest

from agent.service import ReviewService
from evals.dataset_loader import load_samples


@pytest.fixture
def make_service(make_deps):
    """A service whose reviews run on real dependencies around the given fake LLM."""

    def _make(llm=None):
        return ReviewService(
            lambda settings: make_deps(llm, **settings.model_dump(exclude={"data_dir"}))
        )

    return _make


def test_capabilities_say_what_the_tool_supports(make_service, make_llm):
    without_llm = make_service().capabilities()
    with_llm = make_service(make_llm({})).capabilities()

    assert without_llm.services == ["cloud_run", "compute", "cloud_sql", "cloud_storage", "gke"]
    assert without_llm.max_input_kb == 200
    assert "google_storage_bucket" in without_llm.resource_types
    assert without_llm.rule_count == 20
    assert without_llm.llm_configured is False
    assert with_llm.llm_configured is True


SQL_OPEN = next(s for s in load_samples() if s.file == "vulnerable/sql_open.tf")
WRITER = {"PLAN_RESEARCH": {"queries": []}, "WRITE_REPORT": {"summary": "One open database."}}


def test_a_review_reports_each_step_as_it_finishes_then_the_report(make_service, make_llm):
    service = make_service(make_llm(WRITER))

    events = list(service.stream_review(SQL_OPEN.terraform, "shop"))

    steps = [event.step for event in events if event.type == "step"]
    assert steps == ["parse", "security_check", "cost_estimate", "plan_research", "write_report"]
    final = events[-1]
    assert final.type == "report"
    assert {f.rule_id for f in final.report.findings if f.rule_id} == {
        e.rule_id for e in SQL_OPEN.expected_findings
    }
    assert final.waiting_for_feedback is True


def test_input_that_is_not_terraform_is_rejected_with_a_message_not_an_exception(make_service):
    events = list(make_service().stream_review('print("hello")'))

    assert [event.type for event in events] == ["rejected"]
    assert "does not look like Terraform" in events[0].message


def test_advanced_options_apply_to_one_review(make_service, make_llm):
    from agent.service import ReviewOptions

    searching = {
        "PLAN_RESEARCH": {"queries": [{"query": "standby cost", "service": "cloud_sql"}]},
        "GRADE_DOCS": lambda user: {"relevant_ids": []},
        "REWRITE_QUERY": {"queries": []},
        "WRITE_REPORT": {"summary": "One open database."},
    }
    service = make_service(make_llm(searching))

    default = [e.step for e in service.stream_review(SQL_OPEN.terraform)]
    no_search = list(
        service.stream_review(SQL_OPEN.terraform, options=ReviewOptions(use_rag=False))
    )

    assert "retrieve" in default
    assert "retrieve" not in [event.step for event in no_search]
    assert no_search[-1].type == "report"


ADVICE = {
    "summary": "One open database.",
    "recommendations": [
        {
            "resource": "google_sql_database_instance.main",
            "category": "cost",
            "issue": "High availability doubles the cost of this instance.",
            "recommendation": "Use ZONAL availability if this is not production.",
        }
    ],
}


def _review(service, project_id="shop"):
    return list(service.stream_review(SQL_OPEN.terraform, project_id))[-1].report


def _index(report, *, security: bool) -> int:
    return next(
        i for i, f in enumerate(report.findings) if (f.category.value == "security") == security
    )


def test_dismissing_a_suggestion_lowers_it_in_the_next_review(make_service, make_llm):
    from agent.service import FeedbackChoice

    service = make_service(make_llm({"PLAN_RESEARCH": {"queries": []}, "WRITE_REPORT": ADVICE}))
    first = _review(service)
    advice = _index(first, security=False)

    result = service.finish_review(
        first.review_id, [FeedbackChoice(finding_index=advice, action="dismiss")]
    )
    second = _review(service)

    assert (result.status, result.saved, result.ignored) == ("ok", 1, 0)
    assert first.findings[advice].deprioritized is False
    assert [f.deprioritized for f in second.findings if f.category.value != "security"] == [True]


def test_feedback_on_a_security_finding_is_ignored(make_service, make_llm):
    from agent.service import FeedbackChoice

    service = make_service(make_llm({"PLAN_RESEARCH": {"queries": []}, "WRITE_REPORT": ADVICE}))
    first = _review(service)

    result = service.finish_review(
        first.review_id,
        [FeedbackChoice(finding_index=_index(first, security=True), action="dismiss")],
    )
    second = _review(service)

    assert (result.status, result.saved, result.ignored) == ("ok", 0, 1)
    assert not any(f.deprioritized for f in second.findings if f.category.value == "security")
    assert len(second.findings) == len(first.findings)


def test_finishing_an_unknown_or_finished_review_says_so(make_service, make_llm):
    service = make_service(make_llm(WRITER))
    report = _review(service)

    assert service.finish_review("no-such-review", []).status == "not_found"
    assert service.finish_review(report.review_id, []).status == "ok"
    assert service.finish_review(report.review_id, []).status == "already_finished"


def test_project_memory_is_saved_and_used_by_the_next_review(make_service, make_llm):
    from memory.store import ProjectConstraints

    service = make_service(make_llm(WRITER))
    assert service.get_memory("shop").budget_monthly_usd is None

    service.save_memory("shop", ProjectConstraints(budget_monthly_usd=100, region="europe-west1"))
    report = _review(service, "shop")

    assert service.get_memory("shop").region == "europe-west1"
    assert any(f.rule_id == "COST-BUDGET" for f in report.findings)  # the estimate is $231.25


def test_samples_can_be_listed_and_read_but_nothing_else_can(make_service):
    service = make_service()

    assert "mixed/web_stack.tf" in service.samples()
    assert "google_compute_instance" in service.sample("mixed/web_stack.tf")
    assert service.sample("../../.env") is None
    assert service.sample("expected.json") is None
