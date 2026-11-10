"""Evaluation of the full agent with a real LLM: quality, speed and cost per model.

For every model and configuration, every sample is reviewed `runs` times. One record is
saved per review, and `summarize` turns the records into one row per (model, config).

Configurations (ablations):
- `full`:        the agent as designed
- `no_rag`:      documentation search switched off
- `no_rewrite`:  search on, but the rewrite loop disabled (max_rewrites = 0)
- `react`:       not the graph at all, but the ReAct baseline (evals/react_baseline.py):
                 one LLM with function calling over the same tools
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Callable
from typing import Any

from agent.deps import Deps
from agent.graph import DETERMINISTIC_NODES, LLM_NODES
from agent.report import SUGGESTION_PREFIX
from agent.runner import run_review
from agent.state import ReviewReport
from agent.summary import summarize_resources
from evals.dataset_loader import Sample
from evals.judge import Judge, advisory_text, judge_context
from evals.metrics import confusion, latency_stats, mean_or_none, share
from evals.ragas_judge import RagasJudge, ragas_sample
from evals.react_baseline import run_react_review
from rag.ingest import load_chunks
from tools.models import Category, Severity
from tools.tf_parser import parse_terraform

CONFIGS: dict[str, dict[str, Any]] = {
    "full": {},
    "no_rag": {"use_rag": False},
    "no_rewrite": {"max_rewrites": 0},
}
REACT = "react"  # opt-in (`--configs full,react`): a different agent, not a graph setting
JUDGED_CONFIGS = ("full", REACT)  # the judges cost money: only the configs being compared
_URL = re.compile(r"https?://[^\s)\]>\"']+")
_FALLBACK_MARKERS = ("unavailable", "default queries", "skipped", "failed")

DepsFactory = Callable[[str, dict[str, Any]], Deps]
Prices = dict[str, dict[str, float]]


def corpus_urls() -> set[str]:
    return {chunk.source_url for chunk in load_chunks()}


def review_cost_usd(report: ReviewReport, model: str, prices: Prices) -> float | None:
    price = prices.get(model)
    if price is None:
        return None
    usage = report.usage
    cost = usage.input_tokens * price["input"] + usage.output_tokens * price["output"]
    return round(cost / 1e6, 6)


def score_review(report: ReviewReport, sample: Sample, valid_urls: set[str]) -> dict[str, Any]:
    """Everything we can measure about one review without another LLM."""
    security = [f for f in report.findings if f.category == Category.SECURITY]
    advice = [f for f in report.findings if f.category != Category.SECURITY and not f.rule_id]
    result = confusion(
        ((e.resource, e.rule_id) for e in sample.expected_findings),
        ((f.resource, f.rule_id or "") for f in security),
    )
    text = report.model_dump_json(exclude={"evidence"})
    untrusted = [url for url in _URL.findall(text) if url.rstrip(".,") not in valid_urls]
    timings = report.timings
    return {
        "status": report.status,
        "true_positives": result.true_positives,
        "false_positives": result.false_positives,
        "false_negatives": result.false_negatives,
        "critical_findings": sum(1 for f in report.findings if f.severity == Severity.CRITICAL),
        "n_recommendations": len(advice),
        "n_with_valid_source": sum(1 for f in advice if f.source_url in valid_urls),
        "n_suggestions": sum(1 for f in advice if f.recommendation.startswith(SUGGESTION_PREFIX)),
        "n_untrusted_urls": len(untrusted),
        "n_evidence_docs": len(report.evidence),
        "rewrites": report.usage.calls_by_node.get("rewrite_query", 0),
        "tool_calls": {
            name.removeprefix("tool:"): count
            for name, count in report.usage.calls_by_node.items()
            if name.startswith("tool:")
        },
        "llm_fallback": any(m in w for w in report.warnings for m in _FALLBACK_MARKERS),
        "latency_s": timings.get("total"),
        "deterministic_s": round(sum(timings.get(n, 0.0) for n in DETERMINISTIC_NODES), 4),
        "llm_s": round(sum(timings.get(n, 0.0) for n in LLM_NODES), 4),
        "timings": timings,
        "llm_calls": report.usage.llm_calls,
        "input_tokens": report.usage.input_tokens,
        "output_tokens": report.usage.output_tokens,
    }


def judge_input(report: ReviewReport, resources_summary: list[dict]) -> dict[str, Any]:
    """The text the judges are given. It is saved in the record, so a result file can be
    judged again by another judge (evals/rejudge.py) without paying for the reviews."""
    sample = ragas_sample(report, resources_summary)
    return {
        "user_input": sample.user_input,
        "advisory_text": advisory_text(report),
        "judge_context": judge_context(report),
        "rag_advice": sample.response,
        "retrieved_contexts": sample.retrieved_contexts,
    }


def print_progress(line: str) -> None:
    """Print one progress line at once, also when the output goes to a file."""
    print(line, flush=True)


def run_llm_eval(
    models: list[str],
    configs: dict[str, list[str]],
    runs: int,
    samples: list[Sample],
    deps_factory: DepsFactory,
    prices: Prices,
    judge: Judge | None = None,
    ragas_judge: RagasJudge | None = None,
    progress: Callable[[str], None] = print_progress,
) -> list[dict[str, Any]]:
    """Run every (model, config, sample, run) combination and return one record each.

    `configs` maps a model to the configurations to run for it.
    """
    valid_urls = corpus_urls()
    records: list[dict[str, Any]] = []
    for model in models:
        for config in configs[model]:
            deps = deps_factory(model, CONFIGS.get(config, {}))
            for sample in samples:
                for run in range(1, runs + 1):
                    record = {"model": model, "config": config, "file": sample.file,
                              "group": sample.group, "run": run}  # fmt: skip
                    try:
                        if config == REACT:
                            report = run_react_review(sample.terraform, deps)
                        else:
                            report = run_review(sample.terraform, f"eval-{config}", deps=deps)
                        record |= score_review(report, sample, valid_urls)
                        record["cost_usd"] = review_cost_usd(report, model, prices)
                        if config in JUDGED_CONFIGS and run == 1:  # once per sample: cost
                            summary = summarize_resources(parse_terraform(sample.terraform))
                            record["judge_input"] = judge_input(report, summary)
                            for scorer in (judge, ragas_judge):
                                if scorer is not None:
                                    record |= scorer.score(report, summary)
                    except Exception as exc:  # one broken review must not lose the whole run
                        record |= {"status": "crashed", "error": type(exc).__name__}
                    records.append(record)
                    progress(
                        f"{model} | {config} | {sample.file} | run {run}: "
                        f"{record.get('status')} {record.get('latency_s', '')}"
                    )
    return records


def _node_medians(records: list[dict[str, Any]]) -> dict[str, float]:
    names = sorted({name for r in records for name in r["timings"] if name != "total"})
    return {
        name: round(statistics.median(r["timings"].get(name, 0.0) for r in records), 4)
        for name in names
    }


def summarize(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One summary row per (model, config)."""
    rows = []
    keys = dict.fromkeys((r["model"], r["config"]) for r in records)
    for model, config in keys:
        group = [r for r in records if (r["model"], r["config"]) == (model, config)]
        ok = [r for r in group if r.get("status") == "ok"]
        if not ok:
            rows.append({"model": model, "config": config, "n_reviews": len(group), "n_ok": 0})
            continue
        tp = sum(r["true_positives"] for r in ok)
        fp = sum(r["false_positives"] for r in ok)
        fn = sum(r["false_negatives"] for r in ok)
        recommendations = sum(r["n_recommendations"] for r in ok)
        injection = [r for r in ok if r["group"] == "injection"]
        clean = [r for r in ok if r["group"] == "clean"]
        rows.append(
            {
                "model": model,
                "config": config,
                "n_reviews": len(group),
                "n_ok": len(ok),
                "security_precision": share(tp, tp + fp),
                "security_recall": share(tp, tp + fn),
                "critical_findings_on_clean": sum(r["critical_findings"] for r in clean),
                "injection_reviews_intact": share(
                    sum(
                        1
                        for r in injection
                        if r["false_negatives"] == 0 and r["n_untrusted_urls"] == 0
                    ),
                    len(injection),
                ),  # fmt: skip
                "untrusted_urls": sum(r["n_untrusted_urls"] for r in ok),
                # Only meaningful for `react`, where calling the tool is the model's choice.
                "security_tool_skipped": sum(
                    1 for r in ok if config == REACT and not r["tool_calls"].get("check_security")
                ),
                "recommendations_per_review": round(recommendations / len(ok), 2),
                "share_with_valid_source": share(
                    sum(r["n_with_valid_source"] for r in ok), recommendations
                ),
                "llm_fallback_rate": share(sum(1 for r in ok if r["llm_fallback"]), len(ok)),
                "rewrites_per_review": round(statistics.fmean(r["rewrites"] for r in ok), 2),
                "latency": latency_stats([r["latency_s"] for r in ok]),
                "deterministic_median_s": round(
                    statistics.median(r["deterministic_s"] for r in ok), 4
                ),
                "llm_median_s": round(statistics.median(r["llm_s"] for r in ok), 4),
                "node_median_s": _node_medians(ok),
                "input_tokens_mean": round(statistics.fmean(r["input_tokens"] for r in ok)),
                "output_tokens_mean": round(statistics.fmean(r["output_tokens"] for r in ok)),
                "llm_calls_mean": round(statistics.fmean(r["llm_calls"] for r in ok), 2),
                "cost_usd_mean": mean_or_none(r.get("cost_usd") for r in ok),
                "faithfulness_mean": mean_or_none(r.get("faithfulness") for r in ok),
                "answer_relevancy_mean": mean_or_none(r.get("answer_relevancy") for r in ok),
                "n_judged": sum(1 for r in ok if r.get("faithfulness") is not None),
                "ragas_context_precision_mean": mean_or_none(
                    r.get("ragas_context_precision") for r in ok
                ),
                "ragas_faithfulness_mean": mean_or_none(r.get("ragas_faithfulness") for r in ok),
                "n_ragas_judged": sum(1 for r in ok if r.get("ragas_faithfulness") is not None),
            }
        )
    return rows
