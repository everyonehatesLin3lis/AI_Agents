import asyncio
import json

from evals.dataset_loader import load_samples
from mcp_server.server import create_server

SAMPLES = {sample.file: sample for sample in load_samples()}


def call_tool(server, arguments: dict) -> dict:
    result = asyncio.run(server.call_tool("review_gcp_infra", arguments))
    assert result.is_error is False
    return json.loads(result.content[0].text)


def test_tool_is_listed_with_a_description_and_schema(make_deps):
    server = create_server(lambda: make_deps(llm=None))

    tools = asyncio.run(server.list_tools())

    assert [tool.name for tool in tools] == ["review_gcp_infra"]
    assert "before it is applied" in tools[0].description
    assert tools[0].input_schema["required"] == ["terraform"]


def test_tool_returns_findings_cost_and_markdown(make_deps):
    sample = SAMPLES["vulnerable/gcs_public.tf"]
    server = create_server(lambda: make_deps(llm=None))

    result = call_tool(server, {"terraform": sample.terraform, "project_id": "shop"})

    assert result["status"] == "ok"
    rule_ids = {finding["rule_id"] for finding in result["report"]["findings"]}
    assert rule_ids == {e.rule_id for e in sample.expected_findings}
    assert result["report"]["cost_estimate"]["total_monthly_usd"] == sample.expected_cost_usd
    assert "[CRITICAL] GCS-001" in result["markdown"]


def test_non_terraform_input_is_rejected_with_a_clear_message(make_deps):
    server = create_server(lambda: make_deps(llm=None))

    result = call_tool(server, {"terraform": "please review my cloud setup"})

    assert result["status"] == "rejected"
    assert "does not look like Terraform" in result["error"]


def test_bad_project_id_is_rejected(make_deps):
    server = create_server(lambda: make_deps(llm=None))

    result = call_tool(server, {"terraform": "x", "project_id": "../../etc"})

    assert result["status"] == "rejected"


def test_unexpected_failure_returns_an_error_result_not_a_stack_trace():
    def broken_factory():
        raise RuntimeError("database password is hunter2")

    server = create_server(broken_factory)
    sample = SAMPLES["vulnerable/gcs_public.tf"]

    result = call_tool(server, {"terraform": sample.terraform})

    assert result == {"status": "error", "error": "The review failed unexpectedly (RuntimeError)."}
