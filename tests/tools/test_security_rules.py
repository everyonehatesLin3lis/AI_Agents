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


# ------------------------------------------------- which Terraform field triggered it


def _fields(file: str) -> dict[str, list[str]]:
    sample = next(s for s in SAMPLES if s.file == file)
    return {
        f.rule_id: f.terraform_fields for f in check_security(parse_terraform(sample.terraform))
    }


def test_a_finding_names_the_terraform_field_and_the_value_found_there():
    fields = _fields("vulnerable/sql_open.tf")

    assert fields["SQL-001"] == [
        'settings.ip_configuration.authorized_networks.value = "0.0.0.0/0"'
    ]
    assert fields["SQL-002"] == ["settings.ip_configuration.ipv4_enabled = true"]
    assert fields["SQL-005"] == ["deletion_protection = false"]


def test_a_finding_about_a_missing_setting_says_the_field_is_not_set():
    fields = _fields("vulnerable/sql_open.tf")

    assert fields["SQL-004"] == ["settings.backup_configuration.enabled is not set"]
    assert fields["SQL-003"] == [
        "settings.ip_configuration.ssl_mode is not set",
        "settings.ip_configuration.require_ssl is not set",
    ]


def test_a_secret_finding_names_the_variable_but_never_shows_its_value():
    findings = check_security(
        parse_terraform(
            next(s for s in SAMPLES if s.file == "vulnerable/cloud_run_public_secret.tf").terraform
        )
    )
    secret = next(f for f in findings if f.rule_id == "RUN-002")

    assert secret.terraform_fields == [
        'template.containers.env.name = ["DB_PASSWORD", "LOG_LEVEL"]'
    ]
    assert "hunter2-prod" not in secret.model_dump_json()


def test_every_finding_in_the_dataset_names_at_least_one_field():
    for sample in SAMPLES:
        for finding in check_security(parse_terraform(sample.terraform)):
            assert finding.terraform_fields, (sample.file, finding.rule_id)


# ------------------------------------------------ regression: findings that were missed


def _findings(terraform: str) -> dict[str, list]:
    by_rule: dict[str, list] = {}
    for finding in check_security(parse_terraform(terraform)):
        by_rule.setdefault(finding.rule_id, []).append(finding)
    return by_rule


_FULL_SCOPE = '["https://www.googleapis.com/auth/cloud-platform"]'
_HARDENED_CLUSTER = """
  name     = "prod"
  location = "us-central1"
  private_cluster_config {
    enable_private_nodes    = true
    enable_private_endpoint = true
  }
  workload_identity_config {
    workload_pool = "acme.svc.id.goog"
  }
"""


def test_default_service_account_in_an_inline_node_pool_block_is_found():
    # Missed before: GKE-005 only read the cluster's own node_config, not the node pools
    # declared inside the cluster with a `node_pool` block.
    terraform = f"""
resource "google_container_cluster" "primary" {{
  {_HARDENED_CLUSTER}
  node_pool {{
    name = "safe"
    node_config {{
      service_account = google_service_account.nodes.email
      oauth_scopes    = {_FULL_SCOPE}
    }}
  }}
  node_pool {{
    name = "workers"
    node_config {{
      oauth_scopes = {_FULL_SCOPE}
    }}
  }}
}}
"""
    found = _findings(terraform)

    assert list(found) == ["GKE-005"]
    (finding,) = found["GKE-005"]
    assert finding.resource == "google_container_cluster.primary"
    assert "node pool 'workers'" in finding.issue
    assert "safe" not in finding.issue
    assert any("node_pool.node_config.oauth_scopes" in f for f in finding.terraform_fields)


@pytest.mark.parametrize("alias", ["default", "123456789-compute@developer.gserviceaccount.com"])
def test_the_default_service_account_written_out_by_name_is_still_the_default(alias):
    # Missed before: `service_account = "default"` was read as a custom account.
    terraform = f"""
resource "google_container_node_pool" "workers" {{
  name    = "workers"
  cluster = "prod"
  node_config {{
    service_account = "{alias}"
    oauth_scopes    = {_FULL_SCOPE}
  }}
}}
resource "google_compute_instance" "vm" {{
  name         = "vm"
  machine_type = "e2-medium"
  zone         = "us-central1-a"
  service_account {{
    email  = "{alias}"
    scopes = ["cloud-platform"]
  }}
}}
"""
    found = _findings(terraform)

    assert "GKE-005" in found
    assert "GCE-003" in found


def test_a_custom_node_service_account_is_not_reported():
    terraform = f"""
resource "google_container_cluster" "primary" {{
  {_HARDENED_CLUSTER}
  node_pool {{
    name = "workers"
    node_config {{
      service_account = "nodes@acme.iam.gserviceaccount.com"
      oauth_scopes    = {_FULL_SCOPE}
    }}
  }}
}}
"""
    assert _findings(terraform) == {}


# --------------------------------------- regression: remediation text that was wrong


def test_open_control_plane_network_is_told_to_remove_it_not_to_add_the_block():
    # Wrong before: the cluster already had master_authorized_networks_config, and the
    # advice was to add it.
    terraform = """
resource "google_container_cluster" "primary" {
  name     = "prod"
  location = "us-central1"
  enable_autopilot = true
  private_cluster_config {
    enable_private_nodes = true
  }
  master_authorized_networks_config {
    cidr_blocks {
      cidr_block = "0.0.0.0/0"
    }
  }
}
"""
    (finding,) = _findings(terraform)["GKE-001"]

    assert finding.recommendation.startswith("Remove 0.0.0.0/0 from")
    assert "Add master_authorized_networks_config" not in finding.recommendation


def test_public_control_plane_without_the_block_is_told_to_add_it():
    terraform = """
resource "google_container_cluster" "primary" {
  name             = "prod"
  location         = "us-central1"
  enable_autopilot = true
  private_cluster_config {
    enable_private_nodes = true
  }
}
"""
    (finding,) = _findings(terraform)["GKE-001"]

    assert finding.recommendation.startswith("Add master_authorized_networks_config")


def _run_secret(resource_type: str, container_path: tuple[str, str]) -> str:
    opening, closing = container_path
    terraform = f"""
resource "{resource_type}" "api" {{
  name     = "api"
  location = "us-central1"
  template {{
    {opening}
      containers {{
        image = "gcr.io/acme/api"
        env {{
          name  = "API_KEY"
          value = "abc123"
        }}
      }}
    {closing}
  }}
}}
"""
    (finding,) = _findings(terraform)["RUN-002"]
    assert "abc123" not in finding.model_dump_json()
    return finding.recommendation


def test_cloud_run_secret_advice_uses_the_attribute_names_of_the_resource_version():
    # Wrong before: the v1 resource was told to use `value_source`, which only exists
    # in google_cloud_run_v2_service. In v1 the block is called `value_from`.
    v1 = _run_secret("google_cloud_run_service", ("spec {", "}"))
    v2 = _run_secret("google_cloud_run_v2_service", ("", ""))

    assert "value_from" in v1 and "value_source" not in v1
    assert "value_source" in v2 and "value_from" not in v2


@pytest.mark.parametrize(
    ("version", "engine"),
    [
        ("MYSQL_8_0", "mysql"),
        ("POSTGRES_15", "postgres"),
        ("SQLSERVER_2019_STANDARD", "sqlserver"),
        (None, "mysql"),  # the provider's default engine is MySQL
    ],
)
def test_cloud_sql_findings_link_to_the_documentation_of_the_instance_engine(version, engine):
    # Wrong before: every Cloud SQL finding linked to the MySQL documentation.
    line = f'database_version = "{version}"' if version else ""
    terraform = f"""
resource "google_sql_database_instance" "db" {{
  name                = "db"
  region              = "us-central1"
  {line}
  deletion_protection = false
  settings {{
    tier = "db-f1-micro"
    ip_configuration {{
      authorized_networks {{
        value = "0.0.0.0/0"
      }}
    }}
  }}
}}
"""
    found = _findings(terraform)

    assert set(found) == {"SQL-001", "SQL-002", "SQL-003", "SQL-004", "SQL-005"}
    for (finding,) in found.values():
        assert finding.source_url.startswith(f"https://cloud.google.com/sql/docs/{engine}/")
