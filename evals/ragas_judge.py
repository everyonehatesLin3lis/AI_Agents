"""Ragas evaluation of the RAG step: are the retrieved passages useful, and does the
advice built on them stay within what they say?

DeepEval (evals/judge.py) judges the whole advisory text against everything the writer
was given. Ragas here looks only at the retrieval-augmented part: the passages that
`retrieve` and `grade_docs` kept, and the recommendations written from them. Security
findings and the summary are left out on purpose, because they do not come from RAG.
"""

from __future__ import annotations

import json
import os
from typing import Any

os.environ.setdefault("RAGAS_DO_NOT_TRACK", "true")  # no usage data sent to Ragas

from langchain_core.language_models import BaseChatModel  # noqa: E402
from ragas.dataset_schema import SingleTurnSample  # noqa: E402
from ragas.llms import LangchainLLMWrapper  # noqa: E402
from ragas.metrics import Faithfulness, LLMContextPrecisionWithoutReference  # noqa: E402

from agent.state import ReviewReport  # noqa: E402
from evals.judge import TASK  # noqa: E402
from tools.models import Category  # noqa: E402


def rag_advice(report: ReviewReport) -> str:
    """The recommendations the LLM wrote, without rule findings or the summary."""
    return "\n".join(
        f"{finding.resource}: {finding.issue} {finding.recommendation}"
        for finding in report.findings
        if finding.category != Category.SECURITY and finding.rule_id is None
    )


def ragas_sample(report: ReviewReport, resources_summary: list[dict]) -> SingleTurnSample:
    """One Ragas sample: the task, the retrieved passages and the advice built on them."""
    return SingleTurnSample(
        user_input=f"{TASK}\nResources: {json.dumps(resources_summary)}",
        retrieved_contexts=[f"{doc.title}. {doc.text}" for doc in report.evidence],
        response=rag_advice(report),
    )


class RagasJudge:
    """Scores one review with Ragas. Like `Judge`, it records failures and never raises."""

    METRICS = (
        ("ragas_context_precision", LLMContextPrecisionWithoutReference),
        ("ragas_faithfulness", Faithfulness),
    )

    def __init__(self, chat_model: BaseChatModel, name: str) -> None:
        self.name = name
        self._llm = LangchainLLMWrapper(chat_model)

    def score(self, report: ReviewReport, resources_summary: list[dict]) -> dict[str, Any]:
        result: dict[str, Any] = {key: None for key, _ in self.METRICS} | {"ragas_error": None}
        sample = ragas_sample(report, resources_summary)
        if not sample.retrieved_contexts or not sample.response:
            return result | {"ragas_error": "nothing to judge"}
        for key, metric_class in self.METRICS:
            try:
                score = metric_class(llm=self._llm).single_turn_score(sample)
                result[key] = round(float(score), 4)
            except Exception as exc:
                result["ragas_error"] = f"{key}: {type(exc).__name__}"
        return result
