import httpx
import pytest

from tools.billing_api import (
    BillingApiError,
    BillingCatalogClient,
    load_prices,
    prices_from_skus,
)

API_KEY = "test-key-do-not-leak"


def _sku(description: str, nanos: int, regions: list[str], usage: str = "OnDemand") -> dict:
    return {
        "description": description,
        "category": {"usageType": usage},
        "serviceRegions": regions,
        "pricingInfo": [
            {"pricingExpression": {"tieredRates": [{"unitPrice": {"units": "0", "nanos": nanos}}]}}
        ],
    }


SKUS = [
    _sku("E2 Instance Core running in Americas", 22_000_000, ["us-central1", "us-east1"]),
    _sku("E2 Instance Ram running in Americas", 3_000_000, ["us-central1"]),
    _sku("Spot Preemptible E2 Instance Core running in Americas", 6_000_000, ["us-central1"]),
    _sku("E2 Instance Core running in Americas", 9_000_000, ["us-central1"], usage="Commit1Yr"),
    _sku("Balanced PD Capacity", 110_000_000, ["europe-west1"]),
    _sku("Some unrelated SKU", 5, ["us-central1"]),
]


def _client(handler, **kwargs) -> BillingCatalogClient:
    http = httpx.Client(transport=httpx.MockTransport(handler))
    return BillingCatalogClient(API_KEY, http=http, sleep=lambda _: None, **kwargs)


def test_skus_become_regional_prices_and_ignore_spot_and_commitments():
    regional = prices_from_skus(SKUS)

    assert regional["us-central1"] == {
        "compute.e2.vcpu_hour": pytest.approx(0.022),
        "compute.e2.ram_gb_hour": pytest.approx(0.003),
    }
    assert regional["us-east1"] == {"compute.e2.vcpu_hour": pytest.approx(0.022)}
    assert regional["europe-west1"] == {"disk.pd-balanced.gb_month": pytest.approx(0.11)}


def test_live_prices_override_static_ones_and_are_not_marked_outdated():
    prices = load_prices(_client(lambda request: httpx.Response(200, json={"skus": SKUS})))

    assert prices.source == "billing_api"
    assert prices.may_be_outdated is False
    assert prices.unit_price("compute.e2.vcpu_hour", "us-central1") == pytest.approx(0.022)
    # not provided by the API: still served from the static table
    assert prices.unit_price("sql.vcpu_hour", "us-central1") == pytest.approx(0.0413)


def test_pagination_is_followed():
    def handler(request: httpx.Request) -> httpx.Response:
        if "pageToken" in request.url.params:
            return httpx.Response(200, json={"skus": [SKUS[1]]})
        return httpx.Response(200, json={"skus": [SKUS[0]], "nextPageToken": "next"})

    assert len(_client(handler).list_skus("svc")) == 2


def test_transient_errors_are_retried_with_backoff():
    calls: list[int] = []
    waits: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503) if len(calls) < 3 else httpx.Response(200, json={"skus": SKUS})

    http = httpx.Client(transport=httpx.MockTransport(handler))
    client = BillingCatalogClient(API_KEY, http=http, sleep=waits.append, backoff_s=0.5)

    assert len(client.list_skus("svc")) == len(SKUS)
    assert waits == [0.5, 1.0]


def test_falls_back_to_static_prices_when_the_api_keeps_failing():
    prices = load_prices(_client(lambda request: httpx.Response(500), max_retries=2))

    assert prices.source == "static"
    assert prices.may_be_outdated is True
    assert "HTTP 500" in prices.fallback_reason


def test_falls_back_on_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    prices = load_prices(_client(handler, max_retries=1))

    assert prices.source == "static"
    assert "ReadTimeout" in prices.fallback_reason


def test_no_client_means_static_prices():
    prices = load_prices(None)

    assert prices.source == "static"
    assert "GCP_BILLING_API_KEY" in prices.fallback_reason


def test_permission_errors_are_not_retried_and_never_leak_the_key():
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(403, json={"error": {"message": f"key {API_KEY} is invalid"}})

    with pytest.raises(BillingApiError) as error:
        _client(handler).list_skus("svc")

    assert len(calls) == 1
    assert API_KEY not in str(error.value)
