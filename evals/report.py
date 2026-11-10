"""Turn the latest saved results into tables and charts, and put them in the README.

    uv run python -m evals.report

Reads the newest `*_deterministic.json` in evals/results/, the newest `*_llm.json` with
the graph agent alone (model comparison), the newest with a graph ablation, and the
newest that includes the ReAct baseline. Writes the
charts to docs/img/ and replaces the block between the RESULTS markers in README.md.
Every table names the result file it came from, so each number can be traced.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "evals" / "results"
IMG_DIR = ROOT / "docs" / "img"
README = ROOT / "README.md"
START, END = "<!-- RESULTS:START -->", "<!-- RESULTS:END -->"

# Chart style: one hue for magnitude, quiet axes, values written on the bars.
SURFACE, INK, MUTED, GRID, BAR = "#fcfcfb", "#0b0b0b", "#898781", "#e1e0d9", "#2a78d6"


Result = tuple[Path, dict[str, Any]]


def latest(
    kind: str, results_dir: Path = RESULTS_DIR, where: Callable[[dict[str, Any]], bool] = bool
) -> Result | None:
    """Newest result file of `kind` whose content passes `where`."""
    for path in sorted(results_dir.glob(f"*_{kind}.json"), reverse=True):
        data = json.loads(path.read_text(encoding="utf-8"))
        if where(data):
            return path, data
    return None


def _configs(data: dict[str, Any]) -> set[str]:
    return {row["config"] for row in data["summary"] if row.get("n_ok")}


ABLATIONS = {"no_rag", "no_rewrite"}
REACT = "react"

# The three LLM sections can come from different runs. Each is paid for once: the
# ablations on one model, the ReAct baseline on one model, the comparison on several.


def comparison_run(results_dir: Path = RESULTS_DIR) -> Result | None:
    """Newest run of the graph agent alone (`full`, no baseline): the model comparison."""
    return latest(
        "llm", results_dir, lambda data: "full" in _configs(data) and REACT not in _configs(data)
    )


def ablation_run(results_dir: Path = RESULTS_DIR) -> Result | None:
    """Newest run with a graph ablation (`no_rag` or `no_rewrite`)."""
    return latest("llm", results_dir, lambda data: bool(ABLATIONS & _configs(data)))


def react_run(results_dir: Path = RESULTS_DIR) -> Result | None:
    """Newest run that includes the ReAct baseline next to the graph agent."""
    return latest("llm", results_dir, lambda data: REACT in _configs(data))


def table(headers: list[str], rows: list[list[Any]]) -> str:
    def cell(value: Any) -> str:
        if value is None:
            return "n/a"
        return f"{value:.2f}" if isinstance(value, float) else str(value)

    lines = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def bar_panels(path: Path, labels: list[str], panels: list[tuple[str, list[float | None], str]]):
    """Small multiples of horizontal bars: one measure per panel, one shared label axis."""
    height = 0.9 + 0.42 * len(labels)
    figure, axes = plt.subplots(1, len(panels), figsize=(4.2 * len(panels), height), sharey=True)
    axes = [axes] if len(panels) == 1 else list(axes)
    figure.patch.set_facecolor(SURFACE)
    for axis, (title, values, fmt) in zip(axes, panels, strict=True):
        shown = [v or 0.0 for v in values]
        axis.barh(labels, shown, color=BAR, height=0.55)
        axis.set_facecolor(SURFACE)
        axis.set_title(title, fontsize=10, color=INK, loc="left")
        axis.invert_yaxis()
        is_score = fmt == "{:.2f}" and max(shown or [0]) <= 1  # shares and 0-1 scores
        top = 1.0 if is_score else max(shown or [1]) or 1.0
        axis.set_xlim(0, top * 1.45)  # room for the value labels
        axis.xaxis.grid(True, color=GRID, linewidth=0.8)
        axis.set_axisbelow(True)
        axis.tick_params(colors=MUTED, labelsize=8, length=0)
        axis.set_xticklabels([])  # the values are written on the bars
        for label in axis.get_yticklabels():
            label.set_color(INK)
            label.set_fontsize(9)
        for spine in axis.spines.values():
            spine.set_visible(False)
        for index, value in enumerate(values):
            text = "n/a" if value is None else fmt.format(value)
            axis.text(shown[index], index, f" {text}", va="center", fontsize=9, color=INK)
    figure.tight_layout()
    IMG_DIR.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=160, facecolor=SURFACE)
    plt.close(figure)


# ------------------------------------------------------------- deterministic


def deterministic_section(path: Path, data: dict[str, Any]) -> str:
    security, cost, retrieval = data["security"], data["cost"], data["retrieval"]
    latency = data["tool_latency"]
    meta = data["meta"]
    groups = [
        [group, s["true_positives"], s["false_positives"], s["false_negatives"],
         s["precision"], s["recall"], s["f1"]]
        for group, s in {**security["by_group"], "all": security["overall"]}.items()
    ]  # fmt: skip
    retrieval_rows = [
        [label.replace("_", " "), r["hit_rate_at_1"], r["hit_rate_at_2"], r["hit_rate_at_4"],
         r["mrr"]]
        for label, r in retrieval.items() if isinstance(r, dict)
    ]  # fmt: skip
    speed_rows = [
        [name.replace("_", " "), s["n"], f"{s['median_s'] * 1000:.3f}", f"{s['p95_s'] * 1000:.3f}"]
        for name, s in latency.items()
    ]
    bar_panels(
        IMG_DIR / "tool_latency.png",
        [name.replace("_", " ") for name in latency],
        [("Median time per deterministic step (ms)",
          [s["median_s"] * 1000 for s in latency.values()], "{:.2f} ms")],
    )  # fmt: skip
    c = cost["summary"]
    return "\n\n".join(
        [
            "### Deterministic parts (no LLM)",
            f"Source: `evals/results/{path.name}` (run {meta['date_utc']}, "
            f"git commit: {meta['git']['commit']}). {data['n_samples']} samples.",
            "**Security rules** (a finding is a `(resource, rule)` pair):",
            table(["Group", "TP", "FP", "FN", "Precision", "Recall", "F1"], groups),
            f"Critical false positives on the clean samples: "
            f"**{security['critical_false_positives_on_clean']}**.",
            f"**Cost estimator** against {c['n']} hand-calculated totals: mean absolute error "
            f"${c['mean_abs_error_usd']:.2f}, largest error ${c['max_abs_error_usd']:.2f}, "
            f"mean absolute percentage error {c['mean_abs_pct_error']:.2f}%.",
            f"**Retrieval** ({retrieval['n_queries']} queries, one expected document each):",
            table(["Setting", "Hit rate @1", "Hit rate @2", "Hit rate @4", "MRR"], retrieval_rows),
            "**Speed of the deterministic steps:**",
            table(["Step", "Measurements", "Median (ms)", "p95 (ms)"], speed_rows),
            "![Median time per deterministic step](docs/img/tool_latency.png)",
        ]
    )


# ----------------------------------------------------------------------- LLM


def _source(path: Path, meta: dict[str, Any]) -> str:
    return (
        f"Source: `evals/results/{path.name}` (run {meta['date_utc']}, git commit: "
        f"{meta['git']['commit']}). Provider: {meta['provider']}. {meta['n_samples']} samples "
        f"x {meta['runs_per_sample']} runs per configuration. Judge model: "
        f"{meta['judge_model']}. Token prices: {meta['model_price_source']}."
    )


def _usd(value: float | None) -> str | None:
    return None if value is None else f"{value:.5f}"


def llm_section(path: Path, data: dict[str, Any]) -> str:
    meta = data["meta"]
    full = [r for r in data["summary"] if r.get("n_ok") and r["config"] == "full"]
    quality = [
        [r["model"], r["n_ok"], r["security_recall"], r["security_precision"],
         r["critical_findings_on_clean"], r["injection_reviews_intact"],
         r["recommendations_per_review"], r["share_with_valid_source"],
         r["faithfulness_mean"], r["answer_relevancy_mean"], r["llm_fallback_rate"]]
        for r in full
    ]  # fmt: skip
    speed = [
        [r["model"], r["latency"]["median_s"], r["latency"]["p95_s"],
         r["deterministic_median_s"], r["llm_median_s"], r["llm_calls_mean"],
         r["input_tokens_mean"], r["output_tokens_mean"], _usd(r["cost_usd_mean"])]
        for r in full
    ]  # fmt: skip
    nodes = sorted({n for r in full for n in r["node_median_s"]})
    node_rows = [[r["model"], *[r["node_median_s"].get(n, 0.0) for n in nodes]] for r in full]
    bar_panels(
        IMG_DIR / "models.png",
        [r["model"] for r in full],
        [
            ("Median latency per review (s)", [r["latency"]["median_s"] for r in full], "{:.1f} s"),
            ("LLM cost per review (USD)", [r["cost_usd_mean"] for r in full], "${:.5f}"),
            ("Faithfulness (0 to 1)", [r["faithfulness_mean"] for r in full], "{:.2f}"),
        ],
    )
    quality_headers = [
        "Model", "Reviews", "Security recall", "Security precision", "Critical on clean",
        "Injection intact", "Recs / review", "Share with source", "Faithfulness",
        "Answer relevancy", "LLM fallback rate",
    ]  # fmt: skip
    speed_headers = [
        "Model", "Median (s)", "p95 (s)", "Deterministic steps (s)", "LLM steps (s)",
        "LLM calls", "Input tokens", "Output tokens", "USD / review",
    ]  # fmt: skip
    return "\n\n".join(
        [
            "### Full agent, per model",
            _source(path, meta),
            "**Quality** (configuration `full`):",
            table(quality_headers, quality),
            "**Speed and cost** (configuration `full`):",
            table(speed_headers, speed),
            "![Latency, cost and faithfulness per model](docs/img/models.png)",
            "**Median seconds per graph node:**",
            table(["Model", *nodes], node_rows),
        ]
    )


def ablation_section(path: Path, data: dict[str, Any]) -> str:
    meta = data["meta"]
    first = meta["models"][0]
    rows = [r for r in data["summary"] if r.get("n_ok") and r["model"] == first]
    ablation_rows = [
        [r["config"], r["recommendations_per_review"], r["share_with_valid_source"],
         r["rewrites_per_review"], r["latency"]["median_s"], r["llm_calls_mean"],
         _usd(r["cost_usd_mean"]), r["faithfulness_mean"], r["answer_relevancy_mean"]]
        for r in rows
    ]  # fmt: skip
    bar_panels(
        IMG_DIR / "ablations.png",
        [r["config"] for r in rows],
        [
            ("Median latency per review (s)",
             [r["latency"]["median_s"] for r in rows], "{:.1f} s"),
            ("Share of recommendations with a source",
             [r["share_with_valid_source"] for r in rows], "{:.2f}"),
            ("LLM cost per review (USD)", [r["cost_usd_mean"] for r in rows], "${:.5f}"),
        ],
    )  # fmt: skip
    headers = [
        "Configuration", "Recs / review", "Share with source", "Rewrites / review",
        "Median (s)", "LLM calls", "USD / review", "Faithfulness", "Answer relevancy",
    ]  # fmt: skip
    return "\n\n".join(
        [
            f"### Ablations ({first})",
            _source(path, meta),
            table(headers, ablation_rows),
            "![Ablations](docs/img/ablations.png)",
        ]
    )


def react_section(path: Path, data: dict[str, Any]) -> str:
    meta = data["meta"]
    first = meta["models"][0]
    rows = [
        r
        for r in data["summary"]
        if r.get("n_ok") and r["model"] == first and r["config"] in ("full", REACT)
    ]
    names = {"full": "Graph agent", REACT: "ReAct baseline"}
    labels = [names[r["config"]] for r in rows]
    quality = [
        [names[r["config"]], f"{r['n_ok']} / {r['n_reviews']}", r["security_recall"],
         r["security_precision"], r["critical_findings_on_clean"], r["injection_reviews_intact"],
         "n/a" if r["config"] == "full" else r["security_tool_skipped"],
         r["recommendations_per_review"], r["share_with_valid_source"], r["untrusted_urls"]]
        for r in rows
    ]  # fmt: skip
    judged = [
        [names[r["config"]], r["n_judged"], r["faithfulness_mean"], r["answer_relevancy_mean"],
         r.get("n_ragas_judged"), r.get("ragas_context_precision_mean"),
         r.get("ragas_faithfulness_mean")]
        for r in rows
    ]  # fmt: skip
    speed = [
        [names[r["config"]], r["latency"]["median_s"], r["latency"]["p95_s"],
         r["llm_calls_mean"], r["input_tokens_mean"], r["output_tokens_mean"],
         _usd(r["cost_usd_mean"])]
        for r in rows
    ]  # fmt: skip
    bar_panels(
        IMG_DIR / "react.png",
        labels,
        [
            ("Security recall", [r["security_recall"] for r in rows], "{:.2f}"),
            ("Median latency per review (s)", [r["latency"]["median_s"] for r in rows], "{:.1f} s"),
            ("LLM cost per review (USD)", [r["cost_usd_mean"] for r in rows], "${:.5f}"),
        ],
    )
    quality_headers = [
        "Agent", "Reviews ok / run", "Security recall", "Security precision",
        "Critical on clean", "Injection intact", "Security tool skipped", "Recs / review",
        "Share with source", "Links outside the store",
    ]  # fmt: skip
    judged_headers = [
        "Agent", "Reviews judged (DeepEval)", "Faithfulness", "Answer relevancy",
        "Reviews judged (Ragas)", "Ragas context precision", "Ragas faithfulness",
    ]  # fmt: skip
    speed_headers = [
        "Agent", "Median (s)", "p95 (s)", "LLM calls", "Input tokens", "Output tokens",
        "USD / review",
    ]  # fmt: skip
    return "\n\n".join(
        [
            f"### Graph agent against a ReAct baseline ({first})",
            _source(path, meta),
            "**Security and recommendations:**",
            table(quality_headers, quality),
            "**Judged quality** (DeepEval on the whole advisory text, Ragas on the RAG step):",
            table(judged_headers, judged),
            "**Speed and cost:**",
            table(speed_headers, speed),
            "![Graph agent against the ReAct baseline](docs/img/react.png)",
        ]
    )


LLM_PENDING = (
    "### Full agent, per model\n\n"
    "**Not run yet.** No result file exists for the LLM evaluation, so there are no numbers "
    "to show here. Set `OPENROUTER_API_KEY` in `.env`, then run `uv run python -m evals.run` "
    "and `uv run python -m evals.report`. This section, the model comparison and the "
    "ablation tables are then filled in from the saved run."
)


def build() -> str:
    parts = []
    deterministic = latest("deterministic")
    parts.append(
        deterministic_section(*deterministic)
        if deterministic
        else "No deterministic results yet. Run `uv run python -m evals.run`."
    )
    comparison = comparison_run()
    parts.append(llm_section(*comparison) if comparison else LLM_PENDING)
    if ablations := ablation_run():
        parts.append(ablation_section(*ablations))
    if react := react_run():
        parts.append(react_section(*react))
    return "\n\n".join(parts)


def update_readme(section: str) -> bool:
    text = README.read_text(encoding="utf-8") if README.exists() else ""
    if START not in text or END not in text:
        return False
    head, rest = text.split(START, 1)
    tail = rest.split(END, 1)[1]
    README.write_text(f"{head}{START}\n\n{section}\n\n{END}{tail}", encoding="utf-8")
    return True


if __name__ == "__main__":
    content = build()
    (RESULTS_DIR / "SUMMARY.md").write_text(content + "\n", encoding="utf-8")
    updated = update_readme(content)
    print("Wrote evals/results/SUMMARY.md" + (" and updated README.md" if updated else ""))
