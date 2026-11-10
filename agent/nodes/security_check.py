"""Node 2: run the deterministic security rules. Pure code, no LLM.

This node does not read feedback, memory or anything the LLM produced, so none of those
can influence which security findings exist or how severe they are.
"""

from __future__ import annotations

from typing import Any

from agent.deps import Deps
from agent.state import ReviewState
from tools.security_rules import check_security


def make_security_check(deps: Deps):
    def security_check(state: ReviewState) -> dict[str, Any]:
        return {"security_findings": check_security(state.resources)}

    return security_check
