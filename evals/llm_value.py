"""What the LLM adds to a review. Costs nothing to run: no model is called.

    uv run python -m evals.llm_value

Two inputs are compared:

1. The **deterministic report**: every sample reviewed right now with no LLM at all
   (`llm=None`). This is what the tool gives without an API key.
2. The **AI-enriched reports** of the saved model comparison run (the newest
   `*_llm.json` with the `full` configuration). Its records hold the text each model
   wrote, so that text can be measured again without paying for it again.

The security findings and the cost estimate are the same in both by construction (see
`agent.report.verify_security_findings`). The difference is the summary and the cost,
sizing and simplification recommendations, so those are what is measured here:

- how many recommendations a review gets, and how many carry a documentation source;
- how many are **configuration-specific**: the text names a value that is in this
  resource's own configuration (`REGIONAL`, `e2-standard-4`, `100`) or a block the
  configuration lacks (`lifecycle rule`, `autoscaling`). This is a word match, not a
  judgement of quality. It separates "your db-custom-2-7680 instance ..." from advice
  that would read the same for any file;
- what the LLM costs in seconds and USD per review, and how the seconds split over the
  LLM steps.

The result is saved to `evals/results/<date>_llm_value.json`, and the deterministic
report of one sample is written to `docs/examples/` next to its AI-enriched version.
"""

from __future__ import annotations

import json
import re
import statistics
import tempfile
from pathlib import Path
from typing import Any

from agent.config import Settings
from agent.deps import Deps
from agent.graph import LLM_NODES
from agent.report import SUGGESTION_PREFIX, render_markdown
from agent.runner import run_review
from agent.state import ReviewReport
from evals.dataset_loader import Sample, load_samples
from evals.metrics import mean_or_none, share
from memory.store import MemoryStore
from rag.retriever import search_gcp_docs
from tools.models import Category

EXAMPLE_SAMPLE = "mixed/web_stack.tf"
EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "docs" / "examples"
MIN_VALUE_CHARS = 3  # shorter strings ("US") match too much by accident
MIN_NUMBER = 10  # small numbers (count = 1) match too much by accident
MAX_EXAMPLES_PER_MODEL = 3
_RESOURCES_MARK = "Resources: "
_PRESENCE_PREFIX = "has_"


# ----------------------------------------------------------- reading saved text


def facts_by_resource(user_input: str) -> dict[str, dict[str, Any]]:
    """The configuration facts the model was given, read back from a saved record."""
    _, mark, payload = user_input.partition(_RESOURCES_MARK)
    if not mark:
        return {}
    return {item["resource"]: item.get("facts", {}) for item in json.loads(payload)}


def split_advice(advisory_text: str) -> tuple[str, list[str]]:
    """The saved text is the summary on the first line, then one line per recommendation."""
    summary, *recommendations = advisory_text.split("\n")
    return summary, recommendations


def config_terms(facts: dict[str, Any]) -> list[str]:
    """Words that only make sense for this configuration: its values and missing blocks."""
    terms: list[str] = []
    for name, value in facts.items():
        if name.startswith(_PRESENCE_PREFIX):
            terms.append(name.removeprefix(_PRESENCE_PREFIX).replace("_", " "))
        elif isinstance(value, bool):
            continue
        elif isinstance(value, int | float):
            if value >= MIN_NUMBER:
                terms.append(f"{value:g}")
        elif isinstance(value, str) and len(value) >= MIN_VALUE_CHARS:
            terms.append(value)
    return terms


def terms_named(text: str, facts: dict[str, Any]) -> list[str]:
    """Which configuration terms the text names. Whole words, any letter case."""
    return [
        term
        for term in config_terms(facts)
        if re.search(rf"(?<![\w.-]){re.escape(term)}(?![\w-])", text, re.IGNORECASE)
    ]


def recommendation_facts(line: str, facts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """A recommendation line starts with its resource address: use that resource's facts."""
    resource = line.split(": ", 1)[0]
    return facts.get(resource, {})


# ------------------------------------------------------------ the two reports


def deterministic_deps(settings: Settings, memory_dir: Path) -> Deps:
    """The agent with no LLM. Static prices, so the result is reproducible."""
    return Deps(
        settings=settings,
        llm=None,
        store=MemoryStore(memory_dir / "llm_value.sqlite"),
        search=lambda query, service, k: search_gcp_docs(
            query, service, k, store_dir=settings.chroma_dir
        ),
        billing_client=None,
    )


def deterministic_row(sample: Sample, report: ReviewReport) -> dict[str, Any]:
    advice = [f for f in report.findings if f.category != Category.SECURITY and not f.rule_id]
    return {
        "file": sample.file,
        "group": sample.group,
        "security_findings": sum(1 for f in report.findings if f.category == Category.SECURITY),
        "has_cost_estimate": report.cost_estimate is not None,
        "n_recommendations": len(advice),
        "summary_is_fallback": "not available" in report.summary,
        "latency_s": report.timings.get("total"),
    }


def review_without_llm(samples: list[Sample], settings: Settings) -> list[tuple[Sample, Any]]:
    with tempfile.TemporaryDirectory() as memory_dir:
        deps = deterministic_deps(settings, Path(memory_dir))
        return [(sample, run_review(sample.terraform, deps=deps)) for sample in samples]


def enriched_rows(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per saved review whose text was kept, with its recommendations measured."""
    rows = []
    for record in records:
        judged = record.get("judge_input")
        if record.get("config") != "full" or not judged:
            continue
        facts = facts_by_resource(judged["user_input"])
        summary, lines = split_advice(judged["advisory_text"])
        all_facts = {f"{r}.{k}": v for r, values in facts.items() for k, v in values.items()}
        rows.append(
            {
                "model": record["model"],
                "file": record["file"],
                "summary": summary,
                "summary_terms": terms_named(summary, all_facts),
                "recommendations": [
                    {
                        "text": line,
                        "has_source": SUGGESTION_PREFIX not in line,
                        "terms": terms_named(line, recommendation_facts(line, facts)),
                    }
                    for line in lines
                ],
            }
        )
    return rows


# ------------------------------------------------------------------ summaries


def _median(values: list[float]) -> float | None:
    return round(statistics.median(values), 2) if values else None


def model_summary(
    model: str, records: list[dict[str, Any]], rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """`records`: every `full` review of the model. `rows`: those whose text was kept."""
    recommendations = [r for row in rows for r in row["recommendations"]]
    return {
        "model": model,
        "reviews": len(records),
        "reviews_with_text": len(rows),
        "recommendations_per_review": round(
            statistics.mean(r["n_recommendations"] for r in records), 2
        ),
        "share_of_reviews_with_a_recommendation": share(
            sum(1 for r in records if r["n_recommendations"]), len(records)
        ),
        "share_with_source": share(
            sum(r["n_with_valid_source"] for r in records),
            sum(r["n_recommendations"] for r in records),
        ),
        "recommendations_measured": len(recommendations),
        "share_config_specific": share(
            sum(1 for r in recommendations if r["terms"]), len(recommendations)
        ),
        "share_of_summaries_naming_the_config": share(
            sum(1 for row in rows if row["summary_terms"]), len(rows)
        ),
        "faithfulness_mean": mean_or_none(r.get("faithfulness") for r in records),
        "answer_relevancy_mean": mean_or_none(r.get("answer_relevancy") for r in records),
        "latency_median_s": _median([r["latency_s"] for r in records]),
        "deterministic_median_s": _median([r["deterministic_s"] for r in records]),
        "llm_calls_mean": round(statistics.mean(r["llm_calls"] for r in records), 2),
        "cost_usd_mean": mean_or_none(r.get("cost_usd") for r in records),
        "llm_step_median_s": {
            node: _median([r["timings"][node] for r in records if node in r["timings"]])
            for node in LLM_NODES
        },
        "llm_step_share_of_reviews": {
            node: share(sum(1 for r in records if node in r["timings"]), len(records))
            for node in LLM_NODES
        },
    }


def pick_examples(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per model, the sourced recommendations that name the most configuration terms."""
    examples = []
    for model in dict.fromkeys(row["model"] for row in rows):
        candidates = [
            {"model": model, "file": row["file"], **rec}
            for row in rows
            if row["model"] == model
            for rec in row["recommendations"]
            if rec["terms"] and rec["has_source"]
        ]
        candidates.sort(key=lambda rec: -len(rec["terms"]))
        examples += candidates[:MAX_EXAMPLES_PER_MODEL]
    return examples


def build(
    comparison_file: str,
    comparison: dict[str, Any],
    without_llm: list[tuple[Sample, ReviewReport]],
) -> dict[str, Any]:
    records = [r for r in comparison["records"] if r.get("config") == "full"]
    rows = enriched_rows(records)
    deterministic = [deterministic_row(sample, report) for sample, report in without_llm]
    return {
        "source_run": comparison_file,
        "source_run_commit": comparison["meta"]["git"]["commit"],
        "judge_model": comparison["meta"].get("judge_model"),
        "deterministic": {
            "reviews": len(deterministic),
            "security_findings": sum(row["security_findings"] for row in deterministic),
            "reviews_with_cost_estimate": sum(row["has_cost_estimate"] for row in deterministic),
            "recommendations": sum(row["n_recommendations"] for row in deterministic),
            "summaries_written": sum(not row["summary_is_fallback"] for row in deterministic),
            "latency_median_s": _median([row["latency_s"] for row in deterministic]),
            "per_sample": deterministic,
        },
        "models": [
            model_summary(
                model,
                [r for r in records if r["model"] == model],
                [row for row in rows if row["model"] == model],
            )
            for model in comparison["meta"]["models"]
        ],
        "examples": pick_examples(rows),
        "reviews_with_text": rows,
    }


def main() -> None:
    from evals.report import comparison_run
    from evals.run import metadata, save

    found = comparison_run()
    if found is None:
        raise SystemExit("No saved model comparison run. Run `uv run python -m evals.run` first.")
    path, comparison = found
    without_llm = review_without_llm(load_samples(), Settings.from_env())
    payload = {"meta": metadata("llm_value"), **build(path.name, comparison, without_llm)}
    saved = save("llm_value", payload)
    for sample, report in without_llm:
        if sample.file == EXAMPLE_SAMPLE:
            target = EXAMPLES_DIR / "web_stack_review_no_llm.md"
            target.write_text(render_markdown(report) + "\n", encoding="utf-8")
            print(f"Wrote {target.relative_to(EXAMPLES_DIR.parent.parent)}")
    print(f"Saved {saved.relative_to(saved.parent.parent.parent)}")


if __name__ == "__main__":
    main()
