"""Ragas evaluation of the RAG step. The LLM is faked; the review, Chroma and tools are real."""

import json

from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from agent.runner import run_review
from evals.dataset_loader import load_samples
from evals.llm_eval import run_llm_eval, summarize
from evals.ragas_judge import RagasJudge, ragas_sample

SQL_OPEN = next(s for s in load_samples() if s.file == "vulnerable/sql_open.tf")
HA_DOC = "cloud_sql/high-availability"
PLAN = {"queries": [{"query": "cost of a regional standby instance", "service": "cloud_sql"}]}


def _documents(user_prompt: str) -> list[dict]:
    payload = user_prompt.split("<review_data>")[1].split("</review_data>")[0]
    return json.loads(payload)["documents"]


def _keep_ha_docs(user: str) -> dict:
    return {"relevant_ids": [d["id"] for d in _documents(user) if d["id"].startswith(HA_DOC)]}


def _recommend_zonal(user: str) -> dict:
    doc_id = next(d["id"] for d in _documents(user) if d["id"].startswith(HA_DOC))
    return {
        "summary": "One highly available PostgreSQL instance, open to the internet.",
        "recommendations": [
            {
                "resource": "google_sql_database_instance.main",
                "category": "cost",
                "severity": "medium",
                "issue": "High availability doubles the cost of this instance.",
                "recommendation": "Use ZONAL availability if this is not production.",
                "doc_id": doc_id,
            }
        ],
    }


def _recommend_without_documents(user: str) -> dict:
    return {
        "summary": "One database.",
        "recommendations": [
            {
                "resource": "google_sql_database_instance.main",
                "category": "cost",
                "issue": "High availability doubles the cost of this instance.",
                "recommendation": "Use ZONAL availability if this is not production.",
            }
        ],
    }


def _review_with_one_cited_recommendation(make_deps, make_llm):
    llm = make_llm(
        {"PLAN_RESEARCH": PLAN, "GRADE_DOCS": _keep_ha_docs, "WRITE_REPORT": _recommend_zonal}
    )
    return run_review(SQL_OPEN.terraform, deps=make_deps(llm))


def test_ragas_sample_holds_the_task_the_retrieved_passages_and_the_llm_advice(make_deps, make_llm):
    report = _review_with_one_cited_recommendation(make_deps, make_llm)

    sample = ragas_sample(report, [{"type": "google_sql_database_instance"}])

    assert "google_sql_database_instance" in sample.user_input
    assert len(sample.retrieved_contexts) == len(report.evidence) >= 1
    assert all("standby" in text or "availability" in text for text in sample.retrieved_contexts)
    assert "Use ZONAL availability if this is not production." in sample.response
    # Rule findings and the summary are not RAG output, so they are not judged here.
    assert "open to the internet" not in sample.response
    assert "SQL-" not in sample.response


def test_ragas_judge_failure_is_recorded_not_raised(make_deps, make_llm):
    report = _review_with_one_cited_recommendation(make_deps, make_llm)
    judge = RagasJudge(FakeListChatModel(responses=["not json at all"]), "fake-judge")

    scores = judge.score(report, [])

    assert scores["ragas_faithfulness"] is None
    assert scores["ragas_context_precision"] is None
    assert scores["ragas_error"] is not None


class AgreeingRagasJudge(BaseChatModel):
    """A judge model that answers each Ragas prompt in its expected shape and always
    agrees: every statement is supported, every passage is useful. It tests our wiring,
    not the quality of a real judge."""

    prompts: list[str] = []

    @property
    def _llm_type(self) -> str:
        return "fake-ragas-judge"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs) -> ChatResult:
        prompt = str(messages[-1].content)
        self.prompts.append(prompt)
        if "StatementGeneratorOutput" in prompt:
            reply = {"statements": ["High availability doubles the cost."]}
        elif "NLIStatementOutput" in prompt:
            reply = {"statements": [{"statement": "s", "reason": "supported", "verdict": 1}]}
        else:
            reply = {"reason": "the passage was useful", "verdict": 1}
        message = AIMessage(content=json.dumps(reply))
        return ChatResult(generations=[ChatGeneration(message=message)])


def test_ragas_judge_scores_context_precision_and_faithfulness(make_deps, make_llm):
    report = _review_with_one_cited_recommendation(make_deps, make_llm)
    judge = RagasJudge(AgreeingRagasJudge(prompts=[]), "fake-judge")

    scores = judge.score(report, [])

    assert scores["ragas_error"] is None
    assert scores["ragas_context_precision"] == 1.0
    assert scores["ragas_faithfulness"] == 1.0


def test_ragas_judge_skips_a_review_without_retrieved_passages(make_deps, make_llm):
    llm = make_llm({"WRITE_REPORT": _recommend_without_documents})
    report = run_review(SQL_OPEN.terraform, deps=make_deps(llm, use_rag=False))
    model = AgreeingRagasJudge(prompts=[])

    scores = RagasJudge(model, "fake-judge").score(report, [])

    assert scores["ragas_error"] == "nothing to judge"
    assert scores["ragas_faithfulness"] is None
    assert model.prompts == []  # no paid judge call for a review with nothing to judge


def test_eval_loop_records_and_summarises_ragas_scores(make_deps, make_llm):
    llm = make_llm(
        {"PLAN_RESEARCH": PLAN, "GRADE_DOCS": _keep_ha_docs, "WRITE_REPORT": _recommend_zonal}
    )

    records = run_llm_eval(
        models=["fake-model"],
        configs={"fake-model": ["full"]},
        runs=2,
        samples=[SQL_OPEN],
        deps_factory=lambda model, overrides: make_deps(llm, **overrides),
        prices={},
        ragas_judge=RagasJudge(AgreeingRagasJudge(prompts=[]), "fake-judge"),
        progress=lambda line: None,
    )
    row = summarize(records)[0]

    assert records[0]["ragas_faithfulness"] == 1.0
    assert "ragas_faithfulness" not in records[1]  # judged once per sample, like DeepEval
    assert row["ragas_faithfulness_mean"] == 1.0
    assert row["ragas_context_precision_mean"] == 1.0
    assert row["n_ragas_judged"] == 1


def _one_judged_run(make_deps, make_llm, ragas_judge=None):
    llm = make_llm(
        {"PLAN_RESEARCH": PLAN, "GRADE_DOCS": _keep_ha_docs, "WRITE_REPORT": _recommend_zonal}
    )
    return run_llm_eval(
        models=["fake-model"],
        configs={"fake-model": ["full"]},
        runs=1,
        samples=[SQL_OPEN],
        deps_factory=lambda model, overrides: make_deps(llm, **overrides),
        prices={},
        ragas_judge=ragas_judge,
        progress=lambda line: None,
    )


def test_judged_records_keep_the_text_that_was_judged(make_deps, make_llm):
    record = _one_judged_run(make_deps, make_llm)[0]

    saved = record["judge_input"]
    assert "Use ZONAL availability if this is not production." in saved["rag_advice"]
    assert "One highly available PostgreSQL instance" in saved["advisory_text"]
    assert saved["retrieved_contexts"] and saved["judge_context"]
    assert "google_sql_database_instance" in saved["user_input"]


def test_saved_records_can_be_judged_again_without_running_a_review(make_deps, make_llm):
    from evals.rejudge import rejudge

    records = _one_judged_run(make_deps, make_llm)  # saved with no judge at all
    assert "ragas_faithfulness" not in records[0]

    judged = rejudge(records, ragas_judge=RagasJudge(AgreeingRagasJudge(prompts=[]), "new-judge"))

    assert judged[0]["ragas_faithfulness"] == 1.0
    assert judged[0]["ragas_context_precision"] == 1.0
    assert "ragas_faithfulness" not in records[0]  # the saved records are not changed
