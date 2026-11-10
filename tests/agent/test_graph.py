"""Integration tests: a full review through the real graph, tools, Chroma and SQLite.

Only the LLM is faked. Expected values come from evals/dataset/expected.json.
"""

import json

import pytest

from agent.report import SUGGESTION_PREFIX, render_markdown
from agent.runner import ReviewNotPausedError, ReviewSession, run_review
from evals.dataset_loader import load_samples
from memory.store import FeedbackAction, FeedbackItem, ProjectConstraints
from rag.retriever import RetrieverError
from tools.models import Category, Severity
from tools.tf_parser import NotTerraformError

SAMPLES = {sample.file: sample for sample in load_samples()}
SQL_OPEN = SAMPLES["vulnerable/sql_open.tf"]
HA_DOC = "cloud_sql/high-availability"
HA_URL = "https://cloud.google.com/sql/docs/mysql/high-availability"

PLAN = {"queries": [{"query": "cost of a regional standby instance", "service": "cloud_sql"}]}


def _documents(user_prompt: str) -> list[dict]:
    payload = user_prompt.split("<review_data>")[1].split("</review_data>")[0]
    return json.loads(payload)["documents"]


def grade_keeping(prefix: str):
    """A grader that keeps the documents whose id starts with `prefix`."""
    return lambda user: {
        "relevant_ids": [d["id"] for d in _documents(user) if d["id"].startswith(prefix)]
    }


def report_citing(prefix: str, savings: float | None = 115.62):
    """A writer that makes one recommendation and cites the first matching document."""

    def reply(user: str) -> dict:
        doc_id = next(d["id"] for d in _documents(user) if d["id"].startswith(prefix))
        return {
            "summary": "One highly available PostgreSQL instance, open to the internet.",
            "recommendations": [
                {
                    "resource": "google_sql_database_instance.main",
                    "category": "cost",
                    "severity": "medium",
                    "issue": "High availability doubles the cost of this instance.",
                    "recommendation": "Use ZONAL availability if this is not production.",
                    "estimated_savings_usd": savings,
                    "doc_id": doc_id,
                }
            ],
        }

    return reply


def happy_llm(make_llm):
    return make_llm(
        {
            "PLAN_RESEARCH": PLAN,
            "GRADE_DOCS": grade_keeping(HA_DOC),
            "WRITE_REPORT": report_citing(HA_DOC),
        }
    )


def security_pairs(report) -> set[tuple[str, str]]:
    return {(f.resource, f.rule_id) for f in report.findings if f.category == Category.SECURITY}


def expected_pairs(sample) -> set[tuple[str, str]]:
    return {(e.resource, e.rule_id) for e in sample.expected_findings}


# ------------------------------------------------------------------ full review


def test_full_review_combines_rules_cost_and_cited_recommendation(make_deps, make_llm):
    deps = make_deps(happy_llm(make_llm))

    report = run_review(SQL_OPEN.terraform, "shop", deps=deps)

    assert report.status == "ok"
    assert security_pairs(report) == expected_pairs(SQL_OPEN)
    assert report.cost_estimate.total_monthly_usd == pytest.approx(SQL_OPEN.expected_cost_usd)
    recommendation = next(f for f in report.findings if f.category == Category.COST)
    assert recommendation.source_url == HA_URL
    assert recommendation.estimated_savings == pytest.approx(115.62)
    assert HA_URL in report.sources
    assert report.headline.startswith("5 security finding(s): 1 critical")


def test_report_tracks_tokens_and_time_per_node(make_deps, make_llm):
    report = run_review(SQL_OPEN.terraform, deps=make_deps(happy_llm(make_llm)))

    assert report.usage.llm_calls == 3  # plan, grade, write
    assert report.usage.input_tokens == 300
    assert report.usage.output_tokens == 60
    assert {"parse", "security_check", "cost_estimate", "write_report", "total"} <= set(
        report.timings
    )


def test_finished_review_is_saved_to_history(make_deps, make_llm):
    deps = make_deps(happy_llm(make_llm))

    report = run_review(SQL_OPEN.terraform, "shop", deps=deps)

    saved = deps.store.list_reviews("shop")
    assert [review.review_id for review in saved] == [report.review_id]


def test_markdown_report_shows_findings_sources_and_cost(make_deps, make_llm):
    text = render_markdown(run_review(SQL_OPEN.terraform, deps=make_deps(happy_llm(make_llm))))

    assert "[CRITICAL] SQL-001" in text
    assert HA_URL in text
    assert "$231.25 per month" in text
    assert "Prices may be outdated" in text


def test_unsupported_resources_are_listed_not_reviewed(make_deps, make_llm):
    sample = SAMPLES["mixed/web_stack.tf"]
    llm = make_llm({"PLAN_RESEARCH": {"queries": []}, "WRITE_REPORT": {"summary": "A web stack."}})

    report = run_review(sample.terraform, deps=make_deps(llm))

    assert report.unsupported_resources == ["google_pubsub_topic.events"]
    assert any("unsupported type" in warning for warning in report.warnings)
    assert security_pairs(report) == expected_pairs(sample)


# ---------------------------------------------------------- research loop


def test_rewrite_loop_stops_after_two_attempts(make_deps, make_llm):
    llm = make_llm(
        {
            "PLAN_RESEARCH": PLAN,
            "GRADE_DOCS": {"relevant_ids": []},  # nothing is ever good enough
            "REWRITE_QUERY": {"queries": [{"query": "cloud sql pricing", "service": "cloud_sql"}]},
            "WRITE_REPORT": {"summary": "Done.", "recommendations": []},
        }
    )

    report = run_review(SQL_OPEN.terraform, deps=make_deps(llm))

    assert len(llm.calls_for("REWRITE_QUERY")) == 2
    assert len(llm.calls_for("WRITE_REPORT")) == 1
    assert report.status == "ok"


def test_no_rewrite_when_enough_relevant_documents_are_found(make_deps, make_llm):
    llm = happy_llm(make_llm)

    run_review(SQL_OPEN.terraform, deps=make_deps(llm))

    assert llm.calls_for("REWRITE_QUERY") == []


def test_rag_can_be_switched_off_for_ablation(make_deps, make_llm):
    llm = make_llm({"WRITE_REPORT": {"summary": "No research.", "recommendations": []}})

    report = run_review(SQL_OPEN.terraform, deps=make_deps(llm, use_rag=False))

    assert [call["marker"] for call in llm.calls] == ["WRITE_REPORT"]
    assert security_pairs(report) == expected_pairs(SQL_OPEN)


# -------------------------------------------------------- guards on LLM output


def test_recommendation_without_a_document_is_phrased_as_a_suggestion(make_deps, make_llm):
    llm = make_llm(
        {
            "WRITE_REPORT": {
                "summary": "s",
                "recommendations": [
                    {
                        "resource": "google_sql_database_instance.main",
                        "category": "sizing",
                        "severity": "low",
                        "issue": "The instance may be larger than needed.",
                        "recommendation": "Measure usage and pick a smaller tier.",
                        "estimated_savings_usd": 9999,
                        "doc_id": None,
                    }
                ],
            }
        }
    )

    report = run_review(SQL_OPEN.terraform, deps=make_deps(llm, use_rag=False))

    suggestion = next(f for f in report.findings if f.category == Category.SIZING)
    assert suggestion.source_url is None
    assert suggestion.recommendation.startswith(SUGGESTION_PREFIX)
    assert suggestion.estimated_savings == pytest.approx(231.25)  # capped at the line's cost


def test_llm_cannot_invent_resources_sources_or_links(make_deps, make_llm):
    def bad_report(user: str) -> dict:
        return {
            "summary": "Everything is safe. Details at https://evil.example.com/docs",
            "recommendations": [
                {
                    "resource": "google_sql_database_instance.does_not_exist",
                    "category": "cost",
                    "issue": "x",
                    "recommendation": "y",
                },
                {
                    "resource": "google_sql_database_instance.main",
                    "category": "cost",
                    "issue": "See http://evil.example.com/a",
                    "recommendation": "Read https://evil.example.com/b first.",
                    "doc_id": "https://evil.example.com/docs",
                },
            ],
        }

    llm = make_llm({"WRITE_REPORT": bad_report})

    report = run_review(SQL_OPEN.terraform, deps=make_deps(llm, use_rag=False))

    advisory = [f for f in report.findings if f.category != Category.SECURITY]
    assert [f.resource for f in advisory] == ["google_sql_database_instance.main"]
    assert advisory[0].source_url is None
    assert "evil.example.com" not in report.model_dump_json()
    assert security_pairs(report) == expected_pairs(SQL_OPEN)
    assert report.headline.startswith("5 security finding(s)")


def test_llm_cannot_add_or_escalate_security_findings(make_deps, make_llm):
    # "security" and "critical" are not allowed by the schema, so the reply is rejected,
    # retried once and then replaced by the deterministic fallback.
    rejected = {
        "summary": "s",
        "recommendations": [
            {
                "resource": "google_sql_database_instance.main",
                "category": "security",
                "severity": "critical",
                "issue": "made up",
                "recommendation": "made up",
            }
        ],
    }
    llm = make_llm({"WRITE_REPORT": rejected})
    clean = SAMPLES["clean/sql_clean.tf"]

    report = run_review(clean.terraform, deps=make_deps(llm, use_rag=False))

    assert [f for f in report.findings if f.severity == Severity.CRITICAL] == []
    assert security_pairs(report) == set()
    assert len(llm.calls_for("WRITE_REPORT")) == 2


def test_invalid_json_gets_one_repair_attempt(make_deps, make_llm):
    llm = make_llm({"WRITE_REPORT": ["this is not json", {"summary": "Recovered."}]})

    report = run_review(SQL_OPEN.terraform, deps=make_deps(llm, use_rag=False))

    assert report.summary == "Recovered."
    assert report.usage.llm_calls == 2


# -------------------------------------------------------------- prompt injection


@pytest.mark.parametrize("sample", load_samples("injection"), ids=lambda s: s.file)
def test_injection_samples_keep_every_security_finding(sample, make_deps, make_llm):
    obedient = make_llm(  # an LLM that does whatever the injected text asked for
        {
            "PLAN_RESEARCH": {"queries": []},
            "WRITE_REPORT": {
                "summary": "No issues found. See https://evil.example.com/docs",
                "recommendations": [],
            },
        }
    )

    report = run_review(sample.terraform, deps=make_deps(obedient))

    assert security_pairs(report) == expected_pairs(sample)
    assert "evil.example.com" not in report.model_dump_json()
    assert "security finding(s)" in report.headline


@pytest.mark.parametrize("sample", load_samples("injection"), ids=lambda s: s.file)
def test_injected_text_never_reaches_a_prompt(sample, make_deps, make_llm):
    llm = happy_llm(make_llm)
    llm.replies["WRITE_REPORT"] = {"summary": "s", "recommendations": []}

    run_review(sample.terraform, deps=make_deps(llm))

    shown = " ".join(call["user"] for call in llm.calls).lower()
    for phrase in ("ignore all previous", "pre-approved", "ciso", "system override",
                   "new instructions", "evil.example.com", "do not report"):  # fmt: skip
        assert phrase not in shown


# ------------------------------------------------------------- failure handling


def test_review_still_works_without_any_llm(make_deps):
    report = run_review(SQL_OPEN.terraform, deps=make_deps(llm=None))

    assert report.status == "ok"
    assert security_pairs(report) == expected_pairs(SQL_OPEN)
    assert report.cost_estimate.total_monthly_usd == pytest.approx(231.25)
    assert "not available" in report.summary
    assert any("AI recommendations unavailable" in warning for warning in report.warnings)
    assert report.usage.llm_calls == 0


def test_review_survives_an_llm_that_always_fails(make_deps, make_llm):
    error = TimeoutError("request timed out with key sk-secret-123")
    llm = make_llm({"PLAN_RESEARCH": error, "GRADE_DOCS": error, "WRITE_REPORT": error})

    report = run_review(SQL_OPEN.terraform, deps=make_deps(llm))

    assert security_pairs(report) == expected_pairs(SQL_OPEN)
    assert any("TimeoutError" in warning for warning in report.warnings)
    assert "sk-secret-123" not in report.model_dump_json()  # error details never leak


def test_review_survives_a_broken_document_store(make_deps, make_llm):
    def broken_search(query, service, k):
        raise RetrieverError("The documentation store has not been built.")

    deps = make_deps(happy_llm(make_llm))
    deps.search = broken_search
    deps.llm.replies["WRITE_REPORT"] = {"summary": "s", "recommendations": []}

    report = run_review(SQL_OPEN.terraform, deps=deps)

    assert report.status == "ok"
    assert any("has not been built" in warning for warning in report.warnings)


def test_input_that_is_not_terraform_is_rejected_before_any_llm_call(make_deps, make_llm):
    llm = happy_llm(make_llm)

    with pytest.raises(NotTerraformError):
        run_review("gcloud sql instances create main", deps=make_deps(llm))

    assert llm.calls == []


def test_syntax_error_gives_a_failed_report_with_a_clear_message(make_deps, make_llm):
    llm = happy_llm(make_llm)

    report = run_review('resource "google_storage_bucket" "b" {\n  name = \n', deps=make_deps(llm))

    assert report.status == "failed"
    assert "syntax error" in report.summary
    assert llm.calls == []


# --------------------------------------------------- memory and human feedback


def test_project_memory_sets_region_and_budget(make_deps, make_llm):
    deps = make_deps(happy_llm(make_llm))
    deps.store.save_constraints(
        "shop", ProjectConstraints(budget_monthly_usd=100, region="europe-west1")
    )

    report = run_review(SQL_OPEN.terraform, "shop", deps=deps)

    budget = next(f for f in report.findings if f.rule_id == "COST-BUDGET")
    assert "above the project budget of $100.00" in budget.issue
    assert report.cost_estimate.region == "europe-west1"
    assert '"budget_monthly_usd": 100' in deps.llm.calls_for("PLAN_RESEARCH")[0]["user"]


def test_interactive_review_pauses_for_feedback_then_remembers_it(make_deps, make_llm):
    session = ReviewSession(make_deps(happy_llm(make_llm)))

    first = session.start(SQL_OPEN.terraform, "shop")
    assert session.is_waiting(first.review_id)
    assert session.deps.store.list_reviews("shop") == []  # not saved until the human answers

    cost = next(f for f in first.findings if f.category == Category.COST)
    critical = next(f for f in first.findings if f.severity == Severity.CRITICAL)
    session.finish(
        first.review_id,
        [
            FeedbackItem(finding_key=cost.feedback_key, category="cost",
                         action=FeedbackAction.DISMISS, comment="This is production."),
            FeedbackItem(finding_key=critical.feedback_key, category="security",
                         action=FeedbackAction.DISMISS, comment="Ignore this forever."),
        ],
    )  # fmt: skip
    assert not session.is_waiting(first.review_id)
    assert len(session.deps.store.list_reviews("shop")) == 1

    second = session.start(SQL_OPEN.terraform, "shop")

    cost_again = next(f for f in second.findings if f.category == Category.COST)
    assert cost_again.deprioritized is True
    assert second.findings[-1] == cost_again  # moved to the end
    assert security_pairs(second) == expected_pairs(SQL_OPEN)  # dismissal had no effect
    assert all(not f.deprioritized for f in second.findings if f.category == Category.SECURITY)
    assert second.findings[0].severity == Severity.CRITICAL


def test_feedback_is_scoped_to_its_project(make_deps, make_llm):
    session = ReviewSession(make_deps(happy_llm(make_llm)))
    first = session.start(SQL_OPEN.terraform, "shop")
    cost = next(f for f in first.findings if f.category == Category.COST)
    session.finish(
        first.review_id,
        [FeedbackItem(finding_key=cost.feedback_key, category="cost", action="dismiss")],
    )

    other = session.start(SQL_OPEN.terraform, "blog")

    assert all(not f.deprioritized for f in other.findings)


def test_finishing_a_review_twice_is_an_error(make_deps, make_llm):
    session = ReviewSession(make_deps(happy_llm(make_llm)))
    report = session.start(SQL_OPEN.terraform)
    session.finish(report.review_id, [])

    with pytest.raises(ReviewNotPausedError):
        session.finish(report.review_id, [])
