"""LLM-judged quality of the advisory text, using DeepEval.

Two metrics, both between 0 and 1:

- Faithfulness: are the claims in the summary and recommendations supported by what the
  model was given (the retrieved documents, the rule findings and the cost estimate)?
- Answer relevancy: does the text address the task (review this configuration)?

The judge is an LLM too, so it runs through the same provider as the agent. It should
be a different, stronger model than the ones being evaluated, and it is recorded in the
result file. A judge failure is recorded as an error for that review and never stops
the run.
"""

from __future__ import annotations

import json
import os
from typing import Any

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")  # no usage data sent to DeepEval

from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric  # noqa: E402
from deepeval.models.base_model import DeepEvalBaseLLM  # noqa: E402
from deepeval.test_case import LLMTestCase  # noqa: E402
from langchain_core.language_models import BaseChatModel  # noqa: E402

from agent.llm import _extract_json, _text_of  # noqa: E402
from agent.state import ReviewReport  # noqa: E402
from tools.models import Category  # noqa: E402

TASK = (
    "Review this Google Cloud Terraform configuration before it is applied. Give a short "
    "summary and concrete cost, sizing and simplification recommendations."
)


def task_input(resources_summary: list[dict]) -> str:
    """The question both judges are given: the task and the resources under review."""
    return f"{TASK}\nResources: {json.dumps(resources_summary)}"


class ChatModelJudge(DeepEvalBaseLLM):
    """Adapts a LangChain chat model to the interface DeepEval expects."""

    def __init__(self, chat_model: BaseChatModel, name: str) -> None:
        self._chat_model = chat_model
        self._name = name

    def load_model(self) -> BaseChatModel:
        return self._chat_model

    def generate(self, prompt: str, schema: Any = None) -> Any:
        if schema is None:
            return _text_of(self._chat_model.invoke(prompt))
        json_model = self._chat_model.bind(response_format={"type": "json_object"})
        return schema.model_validate(_extract_json(_text_of(json_model.invoke(prompt))))

    async def a_generate(self, prompt: str, schema: Any = None) -> Any:
        return self.generate(prompt, schema)

    def get_model_name(self) -> str:
        return self._name


def advisory_text(report: ReviewReport) -> str:
    """The part of the report the LLM wrote: the summary and its recommendations."""
    lines = [report.summary]
    for finding in report.findings:
        if finding.category != Category.SECURITY and finding.rule_id is None:
            lines.append(f"{finding.resource}: {finding.issue} {finding.recommendation}")
    return "\n".join(line for line in lines if line)


def judge_context(report: ReviewReport) -> list[str]:
    """Everything the writer was given and may legitimately repeat."""
    context = [f"{doc.title}. {doc.text}" for doc in report.evidence]
    for finding in report.findings:
        if finding.category == Category.SECURITY:
            context.append(
                f"Security rule {finding.rule_id} on {finding.resource}: {finding.issue}"
            )
    cost = report.cost_estimate
    if cost is not None:
        context.append(f"Estimated total cost: {cost.total_monthly_usd} USD per month.")
        for line in cost.lines:
            context.append(
                f"{line.resource} costs {line.monthly_usd} USD per month. "
                + " ".join(line.assumptions)
            )
    return context


class Judge:
    def __init__(self, chat_model: BaseChatModel, name: str) -> None:
        self.name = name
        self._model = ChatModelJudge(chat_model, name)

    def score(self, report: ReviewReport, resources_summary: list[dict]) -> dict[str, Any]:
        """Return both scores, or an error string. Never raises."""
        return self.score_text(
            task_input(resources_summary), advisory_text(report), judge_context(report)
        )

    def score_text(self, user_input: str, text: str, context: list[str]) -> dict[str, Any]:
        """Score text that is already extracted, for example from a saved eval record."""
        if not text or not context:
            return {
                "faithfulness": None,
                "answer_relevancy": None,
                "judge_error": "nothing to judge",
            }
        case = LLMTestCase(
            input=user_input,
            actual_output=text,
            retrieval_context=context,
        )
        result: dict[str, Any] = {
            "faithfulness": None,
            "answer_relevancy": None,
            "judge_error": None,
        }
        for key, metric_class in (
            ("faithfulness", FaithfulnessMetric),
            ("answer_relevancy", AnswerRelevancyMetric),
        ):
            try:
                metric = metric_class(model=self._model, async_mode=False, include_reason=False)
                result[key] = round(float(metric.measure(case, _show_indicator=False)), 4)
            except Exception as exc:
                result["judge_error"] = f"{key}: {type(exc).__name__}"
        return result
