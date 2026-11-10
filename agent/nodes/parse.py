"""Node 1: parse the Terraform text into resources. Pure code, no LLM."""

from __future__ import annotations

from typing import Any

from agent.deps import Deps
from agent.report import failed_report
from agent.state import ReviewState
from tools.tf_parser import TerraformInputError, parse_terraform


def make_parse(deps: Deps):
    def parse(state: ReviewState) -> dict[str, Any]:
        try:
            resources = parse_terraform(state.terraform)
        except TerraformInputError as exc:
            # Stop here with a clear message: nothing downstream can work without resources.
            return {
                "parse_failed": True,
                "errors": [str(exc)],
                "report": failed_report(state, str(exc)),
            }
        return {"resources": resources}

    return parse
