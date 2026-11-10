"""The report is the contract between the Python API and the Node.js UI.

The UI's TypeScript types are written by hand, so nothing else would notice when a field
is added to a Pydantic model and not to the UI. This test compares the field names.
"""

import re
from pathlib import Path

import pytest

from agent.service import Capabilities, FinishResult
from agent.state import ReviewReport, UsageSummary
from memory.store import ProjectConstraints
from tools.models import CostEstimate, CostLine, Finding

TYPES = (Path(__file__).resolve().parents[2] / "web" / "lib" / "types.ts").read_text(
    encoding="utf-8"
)
# Report fields the UI does not show, on purpose.
NOT_USED_BY_UI = {"ReviewReport": {"evidence"}}
PAIRS = [
    ("ReviewReport", ReviewReport),
    ("Finding", Finding),
    ("CostEstimate", CostEstimate),
    ("CostLine", CostLine),
    ("Usage", UsageSummary),
    ("Capabilities", Capabilities),
    ("ProjectMemory", ProjectConstraints),
    ("FinishResult", FinishResult),
]


def typescript_fields(type_name: str) -> set[str]:
    body = re.search(rf"export type {type_name} = \{{(.*?)\n\}};", TYPES, re.S)
    assert body, f"type {type_name} not found in web/lib/types.ts"
    return set(re.findall(r"^\s+(\w+)\??:", body.group(1), re.M))


@pytest.mark.parametrize(("type_name", "model"), PAIRS, ids=[name for name, _ in PAIRS])
def test_ui_types_have_the_same_fields_as_the_api_models(type_name, model):
    python_fields = set(model.model_fields) - NOT_USED_BY_UI.get(type_name, set())

    assert typescript_fields(type_name) == python_fields
