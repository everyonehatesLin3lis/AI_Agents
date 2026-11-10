"""Evaluation of the parts that use no LLM: rules, cost estimator, retrieval, tool speed.

These numbers are the same on every run (apart from timings), cost nothing and need no
API key.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from evals.dataset_loader import DATASET_DIR, Sample, default_region, load_samples
from evals.metrics import (
    Confusion,
    confusion,
    cost_errors,
    hit_rate,
    latency_stats,
    mean_reciprocal_rank,
)
from rag.retriever import search_gcp_docs
from tools.cost_estimator import estimate_cost
from tools.models import Severity
from tools.pricing import load_static_prices
from tools.security_rules import check_security
from tools.tf_parser import parse_terraform

RETRIEVAL_KS = (1, 2, 4)
RETRIEVAL_DEPTH = 8


def security_metrics(samples: list[Sample]) -> dict[str, Any]:
    """Precision, recall and F1 of the rules, overall and per group."""
    per_sample = []
    totals: dict[str, Confusion] = {}
    critical_fp_on_clean = 0
    for sample in samples:
        findings = check_security(parse_terraform(sample.terraform))
        result = confusion(
            ((e.resource, e.rule_id) for e in sample.expected_findings),
            ((f.resource, f.rule_id or "") for f in findings),
        )
        totals[sample.group] = totals.get(sample.group, Confusion()) + result
        if sample.group == "clean":
            critical_fp_on_clean += sum(1 for f in findings if f.severity == Severity.CRITICAL)
        per_sample.append({"file": sample.file, **result.scores()})
    overall = sum(totals.values(), Confusion())
    return {
        "overall": overall.scores(),
        "by_group": {group: result.scores() for group, result in sorted(totals.items())},
        "critical_false_positives_on_clean": critical_fp_on_clean,
        "per_sample": per_sample,
    }


def cost_metrics(samples: list[Sample]) -> dict[str, Any]:
    """Error of the estimator against the hand-calculated totals."""
    prices = load_static_prices()
    region = default_region()
    rows = []
    for sample in samples:
        if sample.expected_cost_usd is None:
            continue
        estimate = estimate_cost(parse_terraform(sample.terraform), region, prices)
        rows.append(
            {
                "file": sample.file,
                "expected_usd": sample.expected_cost_usd,
                "estimated_usd": estimate.total_monthly_usd,
            }
        )
    summary = cost_errors([r["expected_usd"] for r in rows], [r["estimated_usd"] for r in rows])
    return {"summary": summary, "per_sample": rows, "price_snapshot": prices.snapshot_date}


def _rank(query: str, service: str | None, expected_doc: str, store_dir: Path) -> int | None:
    docs = search_gcp_docs(query, service, RETRIEVAL_DEPTH, store_dir=store_dir)
    for position, doc in enumerate(docs, start=1):
        if doc.id.split("#")[0] == expected_doc:
            return position
    return None


def retrieval_metrics(store_dir: Path) -> dict[str, Any]:
    """Hit rate of the retriever, with and without the service filter."""
    queries = json.loads((DATASET_DIR / "retrieval_queries.json").read_text("utf-8"))["queries"]
    result: dict[str, Any] = {"n_queries": len(queries)}
    for label, use_filter in (("with_service_filter", True), ("without_service_filter", False)):
        ranks = [
            _rank(q["query"], q["service"] if use_filter else None, q["expected_doc"], store_dir)
            for q in queries
        ]
        result[label] = {
            **{f"hit_rate_at_{k}": hit_rate(ranks, k) for k in RETRIEVAL_KS},
            "mrr": mean_reciprocal_rank(ranks),
            "misses_at_4": [
                q["query"] for q, rank in zip(queries, ranks, strict=True) if not rank or rank > 4
            ],
        }
    return result


def tool_latency(samples: list[Sample], store_dir: Path, repeats: int = 20) -> dict[str, Any]:
    """How long the deterministic steps take, measured `repeats` times per sample."""
    prices = load_static_prices()
    timings: dict[str, list[float]] = {"parse": [], "security_check": [], "cost_estimate": []}
    for sample in samples:
        text = sample.terraform
        for _ in range(repeats):
            start = time.perf_counter()
            resources = parse_terraform(text)
            parsed = time.perf_counter()
            check_security(resources)
            checked = time.perf_counter()
            estimate_cost(resources, "us-central1", prices)
            done = time.perf_counter()
            timings["parse"].append(parsed - start)
            timings["security_check"].append(checked - parsed)
            timings["cost_estimate"].append(done - checked)
    search_gcp_docs("warm up the embedding model", None, 4, store_dir=store_dir)
    retrieve: list[float] = []
    for index in range(repeats):
        start = time.perf_counter()
        search_gcp_docs(f"reduce cost of virtual machines {index}", None, 4, store_dir=store_dir)
        retrieve.append(time.perf_counter() - start)
    timings["retrieve_one_query"] = retrieve
    return {name: latency_stats(values) for name, values in timings.items()}


def run_deterministic(store_dir: Path, repeats: int = 20) -> dict[str, Any]:
    samples = load_samples()
    return {
        "n_samples": len(samples),
        "security": security_metrics(samples),
        "cost": cost_metrics(samples),
        "retrieval": retrieval_metrics(store_dir),
        "tool_latency": tool_latency(samples, store_dir, repeats),
    }
