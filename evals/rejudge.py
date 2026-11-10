"""Judge a saved LLM result file again, with another judge model, without running reviews.

    uv run python -m evals.rejudge evals/results/<stamp>_llm.json --judge-model openai/gpt-5-mini

Every judged record keeps the text the judges were given (`judge_input`). This script
scores that saved text again and writes a new result file; the original is not changed.
Result files saved before `judge_input` existed cannot be judged again.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from ragas.dataset_schema import SingleTurnSample

from agent.config import Settings
from agent.llm import get_chat_model
from evals.judge import Judge
from evals.llm_eval import summarize
from evals.ragas_judge import RagasJudge


def rejudge(
    records: list[dict[str, Any]],
    judge: Judge | None = None,
    ragas_judge: RagasJudge | None = None,
) -> list[dict[str, Any]]:
    """Return copies of `records` with fresh scores for every record that kept its text."""
    result = []
    for record in records:
        fresh = dict(record)
        saved = record.get("judge_input")
        if saved and judge is not None:
            fresh |= judge.score_text(
                saved["user_input"], saved["advisory_text"], saved["judge_context"]
            )
        if saved and ragas_judge is not None:
            fresh |= ragas_judge.score_sample(
                SingleTurnSample(
                    user_input=saved["user_input"],
                    retrieved_contexts=saved["retrieved_contexts"],
                    response=saved["rag_advice"],
                )
            )
        result.append(fresh)
    return result


def main(argv: list[str] | None = None) -> int:
    from evals.run import metadata, save  # imported here: evals.run builds the whole agent

    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("result_file", type=Path)
    parser.add_argument("--judge-model", required=True)
    args = parser.parse_args(argv)

    data = json.loads(args.result_file.read_text(encoding="utf-8"))
    if not any(record.get("judge_input") for record in data["records"]):
        print("This result file has no saved judge input, so it cannot be judged again.")
        return 1
    model = get_chat_model(Settings.from_env().model_copy(update={"model": args.judge_model}))
    if model is None:
        print("No OPENROUTER_API_KEY or OPENAI_API_KEY set.")
        return 1
    records = rejudge(
        data["records"], Judge(model, args.judge_model), RagasJudge(model, args.judge_model)
    )
    meta = {
        **data["meta"],
        "judge_model": args.judge_model,
        "rejudged_from": args.result_file.name,
        "rejudged": metadata("llm"),
    }
    path = save("llm", {"meta": meta, "summary": summarize(records), "records": records})
    print(f"Judged again with {args.judge_model}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
