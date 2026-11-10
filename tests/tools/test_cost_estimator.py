import pytest

from evals.dataset_loader import default_region, load_samples
from tools.cost_estimator import estimate_cost, machine_shape
from tools.pricing import load_static_prices
from tools.tf_parser import parse_terraform

PRICES = load_static_prices()
COSTED = [s for s in load_samples() if s.expected_cost_usd is not None]


def _estimate(terraform: str, region: str = "us-central1"):
    return estimate_cost(parse_terraform(terraform), region, PRICES)


@pytest.mark.parametrize("sample", COSTED, ids=[s.file for s in COSTED])
def test_total_matches_the_hand_calculated_value(sample):
    estimate = _estimate(sample.terraform, default_region())

    assert estimate.total_monthly_usd == pytest.approx(sample.expected_cost_usd, abs=0.01)


def test_count_multiplies_the_line_and_is_listed_as_an_assumption():
    sample = next(s for s in COSTED if s.file == "mixed/web_stack.tf")
    line = next(
        line for line in _estimate(sample.terraform).lines if line.resource.endswith(".app")
    )

    assert line.monthly_usd == pytest.approx(114.21, abs=0.01)
    assert "count = 2." in line.assumptions


def test_static_prices_are_flagged_as_possibly_outdated():
    estimate = _estimate(COSTED[0].terraform)

    assert estimate.prices_may_be_outdated is True
    assert estimate.price_source == "static"
    assert any("may be outdated" in note for note in estimate.notes)


def test_unknown_machine_type_is_not_priced_and_says_so():
    terraform = """
resource "google_compute_instance" "gpu" {
  machine_type = "a2-highgpu-1g"
  zone         = "us-central1-a"
}
"""
    line = _estimate(terraform).lines[0]

    assert line.priced is False
    assert line.monthly_usd == 0
    assert "Unknown machine type 'a2-highgpu-1g'" in line.assumptions[0]


def test_unknown_region_falls_back_to_base_prices_with_a_note():
    terraform = """
resource "google_compute_instance" "vm" {
  machine_type = "e2-medium"
  zone         = "africa-south1-a"
}
"""
    estimate = _estimate(terraform)

    # e2-medium 0.033503 x 730 = 24.46, default boot disk 10 GB pd-standard = 0.40
    assert estimate.total_monthly_usd == pytest.approx(24.86, abs=0.01)
    assert any("africa-south1" in note for note in estimate.notes)


def test_region_argument_is_used_when_the_resource_has_none():
    terraform = """
resource "google_sql_database_instance" "db" {
  settings {
    tier = "db-g1-small"
  }
}
"""
    # (0.035 x 730 + 10 GB x 0.17) x 1.1 for europe-west1 = (25.55 + 1.70) x 1.1
    assert _estimate(terraform, "europe-west1").total_monthly_usd == pytest.approx(29.98, abs=0.01)


@pytest.mark.parametrize(
    ("machine_type", "expected"),
    [
        ("e2-micro", ("e2", 0.25, 1.0)),
        ("n1-standard-2", ("n1", 2.0, 7.5)),
        ("n2-highmem-4", ("n2", 4.0, 32.0)),
        ("e2-custom-4-8192", ("e2", 4.0, 8.0)),
    ],
)
def test_machine_shape(machine_type, expected):
    assert machine_shape(machine_type) == expected
