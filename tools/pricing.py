"""The price table used by the cost estimator.

A `PriceTable` is a flat dictionary of unit prices such as `compute.e2.vcpu_hour`. It can
come from two places: the static JSON file shipped with the project, or the Cloud Billing
Catalog API (see `billing_api.py`), which overlays real per-region prices on top.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

STATIC_PRICES_PATH = Path(__file__).parent / "prices_static.json"


class PriceNotFoundError(KeyError):
    """The price table has no entry for this key."""


class PriceTable(BaseModel):
    source: str = "static"  # "static" or "billing_api"
    snapshot_date: str = ""
    note: str = ""
    base_region: str = "us-central1"
    prices: dict[str, float] = Field(default_factory=dict)
    region_multipliers: dict[str, float] = Field(default_factory=dict)
    # Exact per-region prices (from the Billing API). They win over base x multiplier.
    regional_prices: dict[str, dict[str, float]] = Field(default_factory=dict)
    may_be_outdated: bool = True
    fallback_reason: str | None = None

    def knows_region(self, region: str) -> bool:
        return region in self.region_multipliers or region in self.regional_prices

    def unit_price(self, key: str, region: str) -> float:
        """Price for `key` in `region`. Unknown regions are priced like the base region."""
        exact = self.regional_prices.get(region, {})
        if key in exact:
            return exact[key]
        if key not in self.prices:
            raise PriceNotFoundError(key)
        return self.prices[key] * self.region_multipliers.get(region, 1.0)


def load_static_prices(path: Path = STATIC_PRICES_PATH) -> PriceTable:
    """Load the fallback price table. It is always marked as possibly outdated."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return PriceTable(**data, may_be_outdated=True)
