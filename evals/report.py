"""Turn the latest saved results into tables and charts, and put them in the README.

    uv run python -m evals.report

Reads the newest `*_deterministic.json` and `*_llm.json` in evals/results/. Writes the
charts to docs/img/ and replaces the block between the RESULTS markers in README.md.
Every table names the result file it came from, so each number can be traced.
"""

from __future__ import annotations

import json
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


def latest(kind: str) -> tuple[Path, dict[str, Any]] | None:
    files = sorted(RESULTS_DIR.glob(f"*_{kind}.json"))
    if not files:
        return None
    return files[-1], json.loads(files[-1].read_text(encoding="utf-8"))


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
        axis.set_xlim(0, max(shown or [1]) * 1.45 or 1)  # room for the value labels
        axis.xaxis.grid(True, color=GRID, linewidth=0.8)
        axis.set_axisbelow(True)
        axis.tick_params(colors=MUTED, labelsize=8, length=0)
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


def llm_section(path: Path, data: dict[str, Any]) -> str:
    meta, rows = data["meta"], [r for r in data["summary"] if r.get("n_ok")]
    full = [r for r in rows if r["config"] == "full"]
    first = meta["models"][0]
    ablation = [r for r in rows if r["model"] == first]
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
         r["input_tokens_mean"], r["output_tokens_mean"],
         None if r["cost_usd_mean"] is None else f"{r['cost_usd_mean']:.5f}"]
        for r in full
    ]  # fmt: skip
    ablation_rows = [
        [r["config"], r["recommendations_per_review"], r["share_with_valid_source"],
         r["rewrites_per_review"], r["latency"]["median_s"], r["llm_calls_mean"],
         None if r["cost_usd_mean"] is None else f"{r['cost_usd_mean']:.5f}"]
        for r in ablation
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
    bar_panels(
        IMG_DIR / "ablations.png",
        [r["config"] for r in ablation],
        [
            ("Median latency per review (s)",
             [r["latency"]["median_s"] for r in ablation], "{:.1f} s"),
            ("Share of recommendations with a source",
             [r["share_with_valid_source"] for r in ablation], "{:.2f}"),
            ("LLM cost per review (USD)", [r["cost_usd_mean"] for r in ablation], "${:.5f}"),
        ],
    )  # fmt: skip
    return "\n\n".join(
        [
            "### Full agent, per model",
            f"Source: `evals/results/{path.name}` (run {meta['date_utc']}, git commit: "
            f"{meta['git']['commit']}). Provider: {meta['provider']}. {meta['n_samples']} samples "
            f"x {meta['runs_per_sample']} runs per configuration. Judge model: "
            f"{meta['judge_model']}. Token prices: {meta['model_price_source']}.",
            "**Quality** (configuration `full`):",
            table(
                [
                    "Model",
                    "Reviews",
                    "Security recall",
                    "Security precision",
                    "Critical on clean",
                    "Injection intact",
                    "Recs / review",
                    "Share with source",
                    "Faithfulness",
                    "Answer relevancy",
                    "LLM fallback rate",
                ],
                quality,
            ),  # fmt: skip
            "**Speed and cost** (configuration `full`):",
            table(
                [
                    "Model",
                    "Median (s)",
                    "p95 (s)",
                    "Deterministic steps (s)",
                    "LLM steps (s)",
                    "LLM calls",
                    "Input tokens",
                    "Output tokens",
                    "USD / review",
                ],
                speed,
            ),  # fmt: skip
            "![Latency, cost and faithfulness per model](docs/img/models.png)",
            "**Median seconds per graph node:**",
            table(["Model", *nodes], node_rows),
            f"### Ablations ({first})",
            table(
                [
                    "Configuration",
                    "Recs / review",
                    "Share with source",
                    "Rewrites / review",
                    "Median (s)",
                    "LLM calls",
                    "USD / review",
                ],
                ablation_rows,
            ),  # fmt: skip
            "![Ablations](docs/img/ablations.png)",
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
    llm = latest("llm")
    parts.append(llm_section(*llm) if llm else LLM_PENDING)
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
