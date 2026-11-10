"""Run the eval suite and save the raw results.

    uv run python -m evals.run                        # deterministic + LLM (if a key is set)
    uv run python -m evals.run --deterministic-only   # no API key needed
    uv run python -m evals.run --models xiaomi/mimo-v2.6-flash,deepseek/deepseek-v4-flash --runs 3

Every run writes a new JSON file to evals/results/ with the date, git commit, models,
settings and prices used. Nothing is overwritten, so earlier results stay available.
`uv run python -m evals.report` then turns the latest files into the README tables.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

from agent.config import Settings
from agent.deps import Deps
from agent.llm import get_chat_model, load_model_prices, resolve_provider
from evals.dataset_loader import load_samples
from evals.deterministic import run_deterministic
from evals.judge import Judge
from evals.llm_eval import CONFIGS, REACT, run_llm_eval, summarize
from evals.ragas_judge import RagasJudge
from memory.store import MemoryStore
from rag.ingest import build_store
from rag.retriever import search_gcp_docs

RESULTS_DIR = Path(__file__).parent / "results"
# The models of the saved comparison run (see README, Research method).
DEFAULT_MODELS = [
    "xiaomi/mimo-v2.6-flash",
    "deepseek/deepseek-v4-flash",
    "google/gemini-3.5-flash-lite",
]
DEFAULT_JUDGE = "openai/gpt-5-mini"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"


def git_info() -> dict[str, Any]:
    def git(*args: str) -> str:
        result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
        return result.stdout.strip() if result.returncode == 0 else ""

    commit = git("rev-parse", "HEAD")
    return {"commit": commit or "no commits yet", "dirty": bool(git("status", "--porcelain"))}


def metadata(kind: str, git: dict[str, Any] | None = None) -> dict[str, Any]:
    """Facts about a run. Pass the `git` state captured when the run started: a long run
    must be labelled with the code it used, not with a commit made while it was running."""
    return {
        "kind": kind,
        "date_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "git": git_info() if git is None else git,
        "python": platform.python_version(),
        "platform": platform.platform(),
    }


def save(kind: str, payload: dict[str, Any]) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS_DIR / f"{stamp}_{kind}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def fetch_model_prices(models: list[str]) -> tuple[dict[str, dict[str, float]], str]:
    """Current prices from OpenRouter (USD per 1M tokens), else the bundled snapshot."""
    bundled = load_model_prices()
    try:
        data = httpx.get(OPENROUTER_MODELS_URL, timeout=20).json()["data"]
        live = {
            item["id"]: {
                "input": float(item["pricing"]["prompt"]) * 1e6,
                "output": float(item["pricing"]["completion"]) * 1e6,
            }
            for item in data
            if item["id"] in models
        }
    except Exception:
        return {m: bundled[m] for m in models if m in bundled}, "bundled snapshot"
    missing = {m: bundled[m] for m in models if m not in live and m in bundled}
    return {**missing, **live}, "openrouter live" if not missing else "openrouter live + bundled"


def make_deps_factory(base: Settings, memory_dir: Path):
    def factory(model: str, overrides: dict[str, Any]) -> Deps:
        settings = base.model_copy(update={"model": model, **overrides})
        name = f"{model.replace('/', '_')}_{'_'.join(overrides) or 'full'}.sqlite"
        return Deps(
            settings=settings,
            llm=get_chat_model(settings),
            store=MemoryStore(memory_dir / name),  # fresh memory: runs do not affect each other
            search=lambda query, service, k: search_gcp_docs(
                query, service, k, store_dir=base.chroma_dir
            ),
            billing_client=None,  # static prices, so cost results are reproducible
        )

    return factory


def run_llm_part(args: argparse.Namespace, base: Settings, git: dict[str, Any]) -> Path | None:
    provider = resolve_provider()
    if provider is None:
        print("No OPENROUTER_API_KEY or OPENAI_API_KEY set: skipping the LLM evaluation.")
        return None
    models = [m.strip() for m in args.models.split(",") if m.strip()]
    config_names = [c.strip() for c in args.configs.split(",") if c.strip()]
    if unknown := set(config_names) - set(CONFIGS) - {REACT}:
        raise SystemExit(f"Unknown configuration(s): {', '.join(sorted(unknown))}")
    # Ablations are run for the first model only, to keep the cost of a full run low.
    configs = {m: (config_names if i == 0 else ["full"]) for i, m in enumerate(models)}
    samples = load_samples()[: args.limit] if args.limit else load_samples()
    prices, price_source = fetch_model_prices(models)
    judge = ragas_judge = None
    if not args.no_judge:
        judge_settings = base.model_copy(update={"model": args.judge_model})
        judge_model = get_chat_model(judge_settings)
        judge = Judge(judge_model, args.judge_model)
        ragas_judge = RagasJudge(judge_model, args.judge_model)  # same judge, RAG step only
    with tempfile.TemporaryDirectory() as memory_dir:
        records = run_llm_eval(
            models, configs, args.runs, samples,
            make_deps_factory(base, Path(memory_dir)), prices, judge, ragas_judge,
        )  # fmt: skip
    payload = {
        "meta": {
            **metadata("llm", git),
            "provider": provider.name,
            "models": models,
            "configs": configs,
            "runs_per_sample": args.runs,
            "n_samples": len(samples),
            "judge_model": None if judge is None else judge.name,
            "settings": json.loads(base.model_dump_json(exclude={"model", "data_dir"})),
            "model_prices_usd_per_1m": prices,
            "model_price_source": price_source,
        },
        "summary": summarize(records),
        "records": records,
    }
    return save("llm", payload)


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", default=",".join(DEFAULT_MODELS))
    parser.add_argument(
        "--configs",
        default=",".join(CONFIGS),
        help="for the first model; add `react` to also run the ReAct baseline",
    )
    parser.add_argument("--runs", type=int, default=3, help="reviews per sample and config")
    parser.add_argument("--limit", type=int, default=0, help="use only the first N samples")
    parser.add_argument("--judge-model", default=DEFAULT_JUDGE)
    parser.add_argument(
        "--no-judge", action="store_true", help="skip the DeepEval and Ragas metrics"
    )
    parser.add_argument("--deterministic-only", action="store_true")
    parser.add_argument("--llm-only", action="store_true")
    parser.add_argument("--repeats", type=int, default=20, help="tool timing repetitions")
    args = parser.parse_args(argv)

    git = git_info()  # before any work: the code this run uses
    base = Settings.from_env()
    if not base.chroma_dir.exists():
        print("Building the documentation store first…")
        build_store(base.chroma_dir)

    if not args.llm_only:
        result = run_deterministic(base.chroma_dir, args.repeats)
        path = save("deterministic", {"meta": metadata("deterministic", git), **result})
        security = result["security"]["overall"]
        print(f"Deterministic results saved to {path}")
        print(f"  security precision {security['precision']}, recall {security['recall']}, "
              f"critical false positives on clean: "
              f"{result['security']['critical_false_positives_on_clean']}")  # fmt: skip
    if not args.deterministic_only:
        path = run_llm_part(args, base, git)
        if path:
            print(f"LLM results saved to {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
