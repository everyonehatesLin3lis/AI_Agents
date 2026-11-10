import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from evals.dataset_loader import load_samples
from evals.deterministic import cost_metrics, retrieval_metrics, security_metrics
from evals.judge import Judge, advisory_text
from evals.llm_eval import CONFIGS, review_cost_usd, run_llm_eval, summarize
from evals.metrics import (
    Confusion,
    confusion,
    cost_errors,
    hit_rate,
    latency_stats,
    mean_reciprocal_rank,
    percentile,
)

# ---------------------------------------------------------------- pure metrics


def test_confusion_counts_and_scores():
    result = confusion(
        expected=[("a", "R1"), ("a", "R2"), ("b", "R1")],
        found=[("a", "R1"), ("b", "R1"), ("c", "R9")],
    )

    assert result == Confusion(true_positives=2, false_positives=1, false_negatives=1)
    assert result.precision == pytest.approx(2 / 3)
    assert result.recall == pytest.approx(2 / 3)
    assert result.f1 == pytest.approx(2 / 3)


def test_nothing_expected_and_nothing_found_is_a_perfect_score():
    assert confusion([], []).scores()["precision"] == 1.0
    assert confusion([], []).scores()["recall"] == 1.0


def test_percentile_uses_nearest_rank():
    values = [float(n) for n in range(1, 21)]  # 1..20

    assert percentile(values, 95) == 19.0
    assert percentile(values, 50) == 10.0
    assert percentile([3.0], 95) == 3.0


def test_latency_stats():
    assert latency_stats([1.0, 2.0, 3.0, 10.0]) == {
        "n": 4, "median_s": 2.5, "p95_s": 10.0, "mean_s": 4.0,
    }  # fmt: skip


def test_cost_errors():
    result = cost_errors(expected=[100.0, 50.0], estimated=[110.0, 50.0])

    assert result["mean_abs_error_usd"] == 5.0
    assert result["max_abs_error_usd"] == 10.0
    assert result["mean_abs_pct_error"] == 5.0  # (10% + 0%) / 2


def test_hit_rate_and_mrr():
    ranks = [1, 2, None, 5]

    assert hit_rate(ranks, 1) == 0.25
    assert hit_rate(ranks, 4) == 0.5
    assert mean_reciprocal_rank(ranks) == pytest.approx((1 + 0.5 + 0 + 0.2) / 4)


# ------------------------------------------------- deterministic eval targets


def test_security_rules_meet_the_eval_targets():
    """CLAUDE.md: recall >= 0.9 and zero critical false positives on clean samples."""
    result = security_metrics(load_samples())

    assert result["overall"]["recall"] >= 0.9
    assert result["critical_false_positives_on_clean"] == 0
    assert result["by_group"]["injection"]["recall"] == 1.0


def test_cost_estimates_match_hand_calculated_values():
    assert cost_metrics(load_samples())["summary"]["max_abs_error_usd"] <= 0.01


def test_retrieval_finds_most_expected_documents(chroma_dir):
    result = retrieval_metrics(chroma_dir)

    assert result["n_queries"] >= 30
    assert result["with_service_filter"]["hit_rate_at_4"] >= 0.8


# ----------------------------------------------------- LLM eval loop (fake LLM)


def test_llm_eval_loop_records_and_summarises_every_review(make_deps, make_llm):
    wanted = ("vulnerable/gcs_public.tf", "clean/gcs_clean.tf", "injection/output_hijack.tf")
    samples = [s for s in load_samples() if s.file in wanted]
    llm = make_llm({
        "PLAN_RESEARCH": {"queries": [{"query": "storage classes", "service": "cloud_storage"}]},
        "GRADE_DOCS": {"relevant_ids": []},
        "REWRITE_QUERY": {"queries": [{"query": "lifecycle rules", "service": "cloud_storage"}]},
        "WRITE_REPORT": {"summary": "A bucket.", "recommendations": []},
    })  # fmt: skip
    prices = {"fake-model": {"input": 1.0, "output": 2.0}}

    records = run_llm_eval(
        models=["fake-model"],
        configs={"fake-model": list(CONFIGS)},
        runs=2,
        samples=samples,
        deps_factory=lambda model, overrides: make_deps(llm, **overrides),
        prices=prices,
        judge=None,
        progress=lambda line: None,
    )
    rows = {row["config"]: row for row in summarize(records)}

    assert len(records) == 3 * 3 * 2  # configs x samples x runs
    assert all(record["status"] == "ok" for record in records)
    assert rows["full"]["security_recall"] == 1.0
    assert rows["full"]["critical_findings_on_clean"] == 0
    assert rows["full"]["injection_reviews_intact"] == 1.0
    assert rows["full"]["rewrites_per_review"] == 2.0
    assert rows["no_rewrite"]["rewrites_per_review"] == 0.0
    assert rows["no_rag"]["llm_calls_mean"] == 1.0
    assert rows["full"]["latency"]["n"] == 6
    assert rows["no_rag"]["cost_usd_mean"] == pytest.approx((100 * 1.0 + 20 * 2.0) / 1e6)


def test_unknown_model_price_gives_no_cost_instead_of_a_guess(make_deps):
    from agent.runner import run_review

    report = run_review(load_samples()[0].terraform, deps=make_deps(llm=None))

    assert review_cost_usd(report, "some/unknown-model", {}) is None


def test_judge_scores_a_report_through_deepeval(make_deps, make_llm):
    from agent.runner import run_review

    llm = make_llm({"WRITE_REPORT": {"summary": "One public bucket.", "recommendations": []}})
    report = run_review(load_samples()[0].terraform, deps=make_deps(llm, use_rag=False))
    # A judge model that answers every DeepEval prompt with one JSON object that fits
    # all of its schemas. This tests our wiring, not the quality of a real judge.
    reply = (
        '{"truths": ["a"], "claims": ["a"], "statements": ["a"], '
        '"verdicts": [{"verdict": "yes", "reason": "ok"}], "reason": "ok"}'
    )
    judge = Judge(FakeListChatModel(responses=[reply]), "fake-judge")

    scores = judge.score(report, [])

    assert advisory_text(report) == "One public bucket."
    assert scores == {"faithfulness": 1.0, "answer_relevancy": 1.0, "judge_error": None}


def test_judge_failure_is_recorded_not_raised(make_deps, make_llm):
    from agent.runner import run_review

    llm = make_llm({"WRITE_REPORT": {"summary": "One public bucket.", "recommendations": []}})
    report = run_review(load_samples()[0].terraform, deps=make_deps(llm, use_rag=False))
    judge = Judge(FakeListChatModel(responses=["not json at all"]), "fake-judge")

    scores = judge.score(report, [])

    assert scores["faithfulness"] is None
    assert scores["judge_error"] is not None


# ---------------------------------------------------------------- README report


def _llm_result(models: list[str], configs: list[str]) -> dict:
    row = {"n_ok": 1, "latency": {"median_s": 1.0, "p95_s": 1.0}}
    return {
        "meta": {"models": models},
        "summary": [{**row, "model": m, "config": c} for m in models for c in configs],
    }


def test_report_takes_comparison_and_ablations_from_their_own_latest_runs(tmp_path):
    import json

    from evals.report import ablation_run, comparison_run

    files = {
        "20260101T000000Z_llm.json": _llm_result(["a"], ["full", "no_rag"]),
        "20260102T000000Z_llm.json": _llm_result(["a", "b", "c"], ["full"]),
    }
    for name, data in files.items():
        (tmp_path / name).write_text(json.dumps(data), encoding="utf-8")

    assert comparison_run(tmp_path)[0].name == "20260102T000000Z_llm.json"
    assert ablation_run(tmp_path)[0].name == "20260101T000000Z_llm.json"


def test_report_keeps_the_react_run_apart_from_the_comparison_and_the_ablations(tmp_path):
    import json

    from evals.report import ablation_run, comparison_run, react_run

    files = {
        "20260101T000000Z_llm.json": _llm_result(["a"], ["full", "no_rag"]),
        "20260102T000000Z_llm.json": _llm_result(["a", "b", "c"], ["full"]),
        "20260103T000000Z_llm.json": _llm_result(["a"], ["full", "react"]),
    }
    for name, data in files.items():
        (tmp_path / name).write_text(json.dumps(data), encoding="utf-8")

    assert react_run(tmp_path)[0].name == "20260103T000000Z_llm.json"
    assert comparison_run(tmp_path)[0].name == "20260102T000000Z_llm.json"
    assert ablation_run(tmp_path)[0].name == "20260101T000000Z_llm.json"


def test_result_metadata_carries_the_commit_captured_when_the_run_started():
    from evals.run import metadata

    at_start = {"commit": "abc123", "dirty": False}

    meta = metadata("llm", at_start)  # built at the end of a run, after later commits

    assert meta["git"] == at_start
    assert meta["kind"] == "llm"
