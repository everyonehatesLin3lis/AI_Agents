import pytest

from evals.dataset_loader import load_samples
from tools.models import Category, Severity
from tools.security_rules import RULES, check_security
from tools.tf_parser import parse_terraform

SAMPLES = load_samples()


def _found(terraform: str) -> set[tuple[str, str]]:
    return {(f.resource, f.rule_id) for f in check_security(parse_terraform(terraform))}


@pytest.mark.parametrize("sample", SAMPLES, ids=[s.file for s in SAMPLES])
def test_findings_match_the_labelled_dataset(sample):
    expected = {(e.resource, e.rule_id) for e in sample.expected_findings}

    assert _found(sample.terraform) == expected


@pytest.mark.parametrize("sample", load_samples("clean"), ids=lambda s: s.file)
def test_clean_samples_have_no_critical_findings(sample):
    findings = check_security(parse_terraform(sample.terraform))

    assert [f for f in findings if f.severity == Severity.CRITICAL] == []


def test_public_bucket_is_critical_and_cites_gcp_docs():
    sample = next(s for s in SAMPLES if s.file == "vulnerable/gcs_public.tf")
    finding = next(
        f for f in check_security(parse_terraform(sample.terraform)) if f.rule_id == "GCS-001"
    )

    assert finding.severity == Severity.CRITICAL
    assert finding.category == Category.SECURITY
    assert finding.source_url.startswith("https://cloud.google.com/")
    assert "allUsers" in finding.issue


def test_firewall_port_ranges_and_all_protocols_are_understood():
    terraform = """
resource "google_compute_firewall" "range" {
  allow {
    protocol = "tcp"
    ports    = ["20-25"]
  }
  source_ranges = ["0.0.0.0/0"]
}
resource "google_compute_firewall" "everything" {
  allow {
    protocol = "all"
  }
  source_ranges = ["0.0.0.0/0"]
}
resource "google_compute_firewall" "egress" {
  direction = "EGRESS"
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
  source_ranges = ["0.0.0.0/0"]
}
resource "google_compute_firewall" "internal" {
  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
  source_ranges = ["10.0.0.0/8"]
}
"""
    assert _found(terraform) == {
        ("google_compute_firewall.range", "GCE-001"),
        ("google_compute_firewall.everything", "GCE-001"),
        ("google_compute_firewall.everything", "GCE-002"),
    }


def test_rule_ids_are_unique_and_every_rule_has_a_source():
    ids = [rule.id for rule in RULES]

    assert len(ids) == len(set(ids))
    assert all(rule.source_url.startswith("https://cloud.google.com/") for rule in RULES)


def test_same_input_gives_same_output():
    terraform = SAMPLES[0].terraform

    assert check_security(parse_terraform(terraform)) == check_security(parse_terraform(terraform))
