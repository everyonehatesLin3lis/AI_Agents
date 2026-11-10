"""Client for the public Cloud Billing Catalog API (list prices only, read-only).

This is the only GCP API the project calls. It needs an API key but no GCP credentials
and cannot change anything in a project.

Failure handling (CLAUDE.md "Rules"): every request has a timeout, transient failures are
retried with exponential backoff, and `load_prices` falls back to the static price table
when the API cannot be used. The API key is never put into an error message or a log.

Scope of the live prices: Compute Engine vCPU, memory and persistent disk SKUs (which
also price GKE nodes). Cloud SQL, Cloud Storage, Cloud Run and the GKE fee stay on the
static table. See docs/DECISIONS.md.
"""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from datetime import date
from typing import Any

import httpx

from tools.pricing import PriceTable, load_static_prices

BASE_URL = "https://cloudbilling.googleapis.com/v1"
COMPUTE_SERVICE_ID = "6F81-5844-456A"
RETRY_STATUS = {429, 500, 502, 503, 504}

# SKU description prefix -> key in the price table.
_SKU_KEYS: tuple[tuple[re.Pattern[str], str], ...] = tuple(
    (re.compile(pattern), key)
    for pattern, key in (
        (r"^E2 Instance Core running in", "compute.e2.vcpu_hour"),
        (r"^E2 Instance Ram running in", "compute.e2.ram_gb_hour"),
        (r"^N1 Predefined Instance Core running in", "compute.n1.vcpu_hour"),
        (r"^N1 Predefined Instance Ram running in", "compute.n1.ram_gb_hour"),
        (r"^N2 Instance Core running in", "compute.n2.vcpu_hour"),
        (r"^N2 Instance Ram running in", "compute.n2.ram_gb_hour"),
        (r"^N2D AMD Instance Core running in", "compute.n2d.vcpu_hour"),
        (r"^N2D AMD Instance Ram running in", "compute.n2d.ram_gb_hour"),
        (r"^Storage PD Capacity", "disk.pd-standard.gb_month"),
        (r"^Balanced PD Capacity", "disk.pd-balanced.gb_month"),
        (r"^SSD backed PD Capacity", "disk.pd-ssd.gb_month"),
    )
)


class BillingApiError(Exception):
    """The Billing Catalog API could not be used. The message never contains the key."""


class BillingCatalogClient:
    """Minimal read-only client. `http` and `sleep` are injectable for tests."""

    def __init__(
        self,
        api_key: str,
        *,
        http: httpx.Client | None = None,
        timeout_s: float = 10.0,
        max_retries: int = 3,
        backoff_s: float = 0.5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._api_key = api_key
        self._http = http or httpx.Client(timeout=timeout_s)
        self._max_retries = max_retries
        self._backoff_s = backoff_s
        self._sleep = sleep

    def list_skus(self, service_id: str) -> list[dict[str, Any]]:
        """Return every SKU of a service, following pagination."""
        skus: list[dict[str, Any]] = []
        page_token = ""
        while True:
            page = self._get_page(service_id, page_token)
            skus.extend(page.get("skus", []))
            page_token = page.get("nextPageToken", "")
            if not page_token:
                return skus

    def _get_page(self, service_id: str, page_token: str) -> dict[str, Any]:
        url = f"{BASE_URL}/services/{service_id}/skus"
        params = {"key": self._api_key, "pageSize": "5000", "currencyCode": "USD"}
        if page_token:
            params["pageToken"] = page_token
        last_problem = "unknown error"
        for attempt in range(self._max_retries + 1):
            if attempt:
                self._sleep(self._backoff_s * 2 ** (attempt - 1))
            try:
                response = self._http.get(url, params=params)
            except httpx.HTTPError as exc:
                last_problem = type(exc).__name__  # never str(exc): it can contain the URL
                continue
            if response.status_code == 200:
                return response.json()
            last_problem = f"HTTP {response.status_code}"
            if response.status_code not in RETRY_STATUS:
                break
        raise BillingApiError(f"Billing Catalog API request failed ({last_problem}).")


def load_prices(client: BillingCatalogClient | None) -> PriceTable:
    """Return live prices when possible, otherwise the static table with a reason."""
    static = load_static_prices()
    if client is None:
        static.fallback_reason = "No GCP_BILLING_API_KEY configured."
        return static
    try:
        skus = client.list_skus(COMPUTE_SERVICE_ID)
    except BillingApiError as exc:
        static.fallback_reason = str(exc)
        return static
    regional = prices_from_skus(skus)
    if not regional:
        static.fallback_reason = "Billing Catalog API returned no usable SKUs."
        return static
    return static.model_copy(
        update={
            "source": "billing_api",
            "snapshot_date": date.today().isoformat(),
            "regional_prices": regional,
            "may_be_outdated": False,
            "note": "Compute Engine prices from the Cloud Billing Catalog API; other "
            "services from the static table.",
        }
    )


def prices_from_skus(skus: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Turn raw SKUs into `{region: {price key: unit price}}`. Unknown SKUs are ignored."""
    regional: dict[str, dict[str, float]] = {}
    for sku in skus:
        key = _price_key(sku)
        price = _unit_price(sku)
        if key is None or price is None:
            continue
        for region in sku.get("serviceRegions", []):
            regional.setdefault(region, {})[key] = price
    return regional


def _price_key(sku: dict[str, Any]) -> str | None:
    if sku.get("category", {}).get("usageType") != "OnDemand":
        return None
    description = sku.get("description", "")
    for pattern, key in _SKU_KEYS:
        if pattern.search(description):
            return key
    return None


def _unit_price(sku: dict[str, Any]) -> float | None:
    """Highest tier price in USD (the first tier is sometimes a free allowance)."""
    try:
        rates = sku["pricingInfo"][0]["pricingExpression"]["tieredRates"]
        prices = [
            int(rate["unitPrice"].get("units", 0) or 0) + rate["unitPrice"].get("nanos", 0) / 1e9
            for rate in rates
        ]
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return max(prices) if prices and max(prices) > 0 else None
