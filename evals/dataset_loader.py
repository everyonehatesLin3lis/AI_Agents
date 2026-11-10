"""Load the fixed eval dataset. Used by the eval runner and by the tests."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

DATASET_DIR = Path(__file__).parent / "dataset"


class ExpectedFinding(BaseModel, frozen=True):
    resource: str
    rule_id: str


class Sample(BaseModel):
    file: str
    group: str
    expected_findings: list[ExpectedFinding]
    expected_cost_usd: float | None
    unsupported: list[str]

    @property
    def terraform(self) -> str:
        return read_terraform(DATASET_DIR / self.file)


def read_terraform(path: Path) -> str:
    """Read a .tf file. `utf-8-sig` drops the BOM that Windows editors add."""
    return path.read_text(encoding="utf-8-sig")


def load_samples(group: str | None = None) -> list[Sample]:
    data = json.loads((DATASET_DIR / "expected.json").read_text(encoding="utf-8"))
    samples = [Sample(**item) for item in data["samples"]]
    return [sample for sample in samples if group is None or sample.group == group]


def default_region() -> str:
    data = json.loads((DATASET_DIR / "expected.json").read_text(encoding="utf-8"))
    return data["default_region"]
