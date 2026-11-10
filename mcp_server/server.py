"""MCP server that exposes the review as one tool: `review_gcp_infra`.

A coding agent (for example Claude Code) calls this tool with the Terraform it is about
to apply and gets back the report as Markdown plus the same data as JSON.

Run with:  uv run python -m mcp_server.server      (stdio transport)

The tool is read-only. It never touches a GCP project and needs no GCP credentials.
Errors are returned as a normal result with a clear message, so the calling agent can
tell the user what went wrong instead of seeing a stack trace.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from mcp.server.mcpserver import MCPServer

from agent.deps import Deps, default_deps
from agent.report import render_markdown
from agent.runner import run_review
from tools.tf_parser import TerraformInputError

_PROJECT_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
INSTRUCTIONS = (
    "Use review_gcp_infra before applying Terraform for Google Cloud. Pass the full "
    "contents of the .tf file(s) as text. The result lists security findings (decided by "
    "fixed rules), a monthly cost estimate and cited cost recommendations. The review is "
    "read-only and covers Cloud Run, Compute Engine, Cloud SQL, Cloud Storage and GKE."
)


def review(terraform: str, project_id: str, deps_factory: Callable[[], Deps]) -> dict[str, Any]:
    """Run a review and turn every outcome, including failures, into a result dict."""
    if not _PROJECT_ID.match(project_id):
        return _problem("rejected", "project_id may only contain letters, digits, '_', '.', '-'.")
    try:
        report = run_review(terraform, project_id, deps=deps_factory())
    except TerraformInputError as exc:
        return _problem("rejected", str(exc))
    except Exception as exc:  # last line of defence: never return a stack trace
        return _problem("error", f"The review failed unexpectedly ({type(exc).__name__}).")
    return {
        "status": report.status,
        "markdown": render_markdown(report),
        "report": report.model_dump(mode="json"),
    }


def _problem(status: str, message: str) -> dict[str, Any]:
    return {"status": status, "error": message}


def create_server(deps_factory: Callable[[], Deps] = default_deps) -> MCPServer:
    """Build the server. Tests pass a `deps_factory` with a fake LLM."""
    server = MCPServer("gcp-infra-review", instructions=INSTRUCTIONS)

    @server.tool()
    def review_gcp_infra(terraform: str, project_id: str = "default") -> dict[str, Any]:
        """Review Terraform for Google Cloud before it is applied.

        Returns security findings, a monthly cost estimate and cheaper or simpler
        alternatives with links to the Google Cloud documentation.

        Args:
            terraform: The contents of one or more .tf files, as text (max 200 KB).
            project_id: Optional name used to load this project's budget, region and
                preferences from memory.
        """
        return review(terraform, project_id, deps_factory)

    return server


if __name__ == "__main__":
    create_server().run()
