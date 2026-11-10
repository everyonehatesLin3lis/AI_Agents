"""How past feedback changes a report. This is the whole policy, in one small file.

The rule (CLAUDE.md "Rules"): security findings are deterministic and cannot be
overridden. Feedback may only lower the priority of cost, sizing and simplification
suggestions. So:

- A dismissed cost/sizing/simplification suggestion is kept in the report, marked
  `deprioritized` and sorted to the end.
- Feedback that targets a security finding is ignored, whatever it says.
- Nothing is ever removed and no severity is ever changed.
"""

from __future__ import annotations

from memory.store import FeedbackAction, FeedbackItem
from tools.models import SEVERITY_ORDER, Category, Finding

PROTECTED_CATEGORIES = frozenset({Category.SECURITY})


def dismissed_keys(feedback: list[FeedbackItem]) -> set[str]:
    """Keys the user has dismissed. A later "helpful" on the same key cancels a dismiss."""
    latest: dict[str, FeedbackAction] = {}
    for item in feedback:
        latest[item.finding_key] = item.action
    return {key for key, action in latest.items() if action == FeedbackAction.DISMISS}


def apply_feedback(findings: list[Finding], feedback: list[FeedbackItem]) -> list[Finding]:
    """Return the findings with dismissed suggestions deprioritized, then sorted."""
    dismissed = dismissed_keys(feedback)
    result = [
        finding.model_copy(update={"deprioritized": _can_deprioritize(finding, dismissed)})
        for finding in findings
    ]
    return sort_findings(result)


def _can_deprioritize(finding: Finding, dismissed: set[str]) -> bool:
    if finding.category in PROTECTED_CATEGORIES:
        return False
    return finding.feedback_key in dismissed


def sort_findings(findings: list[Finding]) -> list[Finding]:
    """Active findings first, by severity. Deprioritized ones last. Stable otherwise."""
    return sorted(findings, key=lambda f: (f.deprioritized, SEVERITY_ORDER[f.severity]))
