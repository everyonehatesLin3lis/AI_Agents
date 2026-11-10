"""Domain models shared by the tools, the agent, the UI and the MCP server.

Everything that crosses a boundary (tool -> node, node -> UI, agent -> MCP client) is a
Pydantic model, so bad data fails loudly at the boundary instead of deep inside a node.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Service(StrEnum):
    """The five GCP services in scope (see CLAUDE.md, "Scope")."""

    CLOUD_RUN = "cloud_run"
    COMPUTE = "compute"
    CLOUD_SQL = "cloud_sql"
    CLOUD_STORAGE = "cloud_storage"
    GKE = "gke"


class Severity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


SEVERITY_ORDER: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
}


class Category(StrEnum):
    """What kind of finding this is. Only SECURITY findings are protected from feedback."""

    SECURITY = "security"
    COST = "cost"
    SIZING = "sizing"
    SIMPLIFICATION = "simplification"


class Resource(BaseModel):
    """One Terraform `resource` block."""

    type: str
    name: str
    service: Service | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)

    @property
    def address(self) -> str:
        """Terraform address, e.g. `google_storage_bucket.assets`."""
        return f"{self.type}.{self.name}"

    @property
    def supported(self) -> bool:
        return self.service is not None


class Finding(BaseModel):
    """One item in the review report.

    The six fields required by the project brief come first. `rule_id`, `category` and
    `deprioritized` are extras used for evaluation and for the feedback policy.
    """

    severity: Severity
    resource: str
    issue: str
    recommendation: str
    estimated_savings: float | None = None  # USD per month
    source_url: str | None = None
    rule_id: str | None = None
    category: Category = Category.SECURITY
    deprioritized: bool = False

    @property
    def feedback_key(self) -> str:
        """Stable key used to match user feedback to future findings of the same kind."""
        resource_type = self.resource.split(".", 1)[0]
        return self.rule_id or f"{self.category.value}:{resource_type}"


class CostLine(BaseModel):
    resource: str
    service: Service
    monthly_usd: float
    priced: bool = True  # False when we could not price it (unknown machine type, etc.)
    assumptions: list[str] = Field(default_factory=list)


class CostEstimate(BaseModel):
    lines: list[CostLine] = Field(default_factory=list)
    total_monthly_usd: float = 0.0
    currency: str = "USD"
    default_region: str  # used only for resources that do not set their own location
    regions_used: list[str] = Field(default_factory=list)  # regions actually priced
    price_source: str  # "billing_api" or "static"
    prices_may_be_outdated: bool = False
    notes: list[str] = Field(default_factory=list)


class Doc(BaseModel):
    """One retrieved chunk of GCP documentation."""

    id: str
    title: str
    service: str
    source_url: str
    text: str
    score: float = 0.0  # cosine similarity, higher is better
