"""Deterministic security rules. Pure code, no LLM.

Each rule is a small function that looks at one resource and returns a short description
of the problem, or None when the resource is fine. Rules live in the `RULES` registry,
so the list in the README is generated from the same data the agent runs.

These findings are the part of the report that must never change because of user
feedback, project memory or anything written inside the Terraform file. Nothing in this
module reads comments, calls an LLM or looks at feedback.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from tools.models import Category, Finding, Resource, Severity
from tools.tf_values import all_blocks, as_bool, dig, first_block, literal_str, string_list

PUBLIC_MEMBERS = {"allUsers", "allAuthenticatedUsers"}
ANY_ADDRESS = {"0.0.0.0/0", "::/0"}
ADMIN_PORTS = {22: "SSH", 3389: "RDP"}
DATABASE_PORTS = {
    1433: "SQL Server",
    3306: "MySQL",
    5432: "PostgreSQL",
    6379: "Redis",
    9200: "Elasticsearch",
    27017: "MongoDB",
}
SECRET_NAME = re.compile(r"(PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY|PRIVATE_?KEY|CREDENTIAL)", re.I)
DEFAULT_COMPUTE_SA = "-compute@developer.gserviceaccount.com"

Check = Callable[[Resource], str | None]


@dataclass(frozen=True)
class Rule:
    id: str
    severity: Severity
    resource_types: tuple[str, ...]
    title: str
    recommendation: str
    source_url: str
    check: Check


# --------------------------------------------------------------------------- helpers


def _members(attributes: dict[str, Any]) -> set[str]:
    members = set(string_list(attributes.get("members")))
    single = literal_str(attributes.get("member"))
    if single:
        members.add(single)
    return members


def _public_members(attributes: dict[str, Any]) -> set[str]:
    return _members(attributes) & PUBLIC_MEMBERS


def _port_in_spec(port: int, spec: str) -> bool:
    """`spec` is a single port ("22") or a range ("1000-2000")."""
    low, _, high = spec.partition("-")
    try:
        return int(low) <= port <= int(high or low)
    except ValueError:
        return False


def _open_ports(resource: Resource, wanted: dict[int, str]) -> list[str]:
    """Names of the `wanted` ports this firewall rule opens to the whole internet."""
    attributes = resource.attributes
    if literal_str(attributes.get("direction")) == "EGRESS" or as_bool(attributes.get("disabled")):
        return []
    if not ANY_ADDRESS & set(string_list(attributes.get("source_ranges"))):
        return []
    opened: list[str] = []
    for allow in all_blocks(attributes, "allow"):
        protocol = (literal_str(allow.get("protocol")) or "").lower()
        ports = string_list(allow.get("ports"))
        if protocol not in ("all", "tcp"):
            continue
        for port, name in wanted.items():
            every_port = protocol == "all" or not ports
            if every_port or any(_port_in_spec(port, spec) for spec in ports):
                opened.append(f"{name} ({port})")
    return sorted(set(opened))


def _uses_default_sa_with_full_scope(service_account: dict[str, Any], scopes: Any) -> bool:
    has_full_scope = any(s.endswith("cloud-platform") for s in string_list(scopes))
    email = service_account.get("email", service_account.get("service_account"))
    if isinstance(email, str) and DEFAULT_COMPUTE_SA not in email:
        return False  # a custom service account (literal or reference) is set
    return has_full_scope


# ------------------------------------------------------------------- Cloud Storage


def _gcs_public_iam(resource: Resource) -> str | None:
    attributes = resource.attributes
    public = _public_members(attributes)
    entity = literal_str(attributes.get("entity"))
    if entity in PUBLIC_MEMBERS:
        public.add(entity)
    for role_entity in string_list(attributes.get("role_entity")):
        if role_entity.split(":")[-1] in PUBLIC_MEMBERS:
            public.add(role_entity.split(":")[-1])
    if not public:
        return None
    return f"Bucket access is granted to {', '.join(sorted(public))}: anyone on the internet."


def _gcs_no_uniform_access(resource: Resource) -> str | None:
    if as_bool(resource.attributes.get("uniform_bucket_level_access")) is True:
        return None
    return "Uniform bucket-level access is not enabled, so per-object ACLs can expose data."


def _gcs_no_public_access_prevention(resource: Resource) -> str | None:
    if literal_str(resource.attributes.get("public_access_prevention")) == "enforced":
        return None
    return "Public access prevention is not enforced on this bucket."


def _gcs_no_versioning(resource: Resource) -> str | None:
    if as_bool(first_block(resource.attributes, "versioning").get("enabled")) is True:
        return None
    return "Object versioning is off, so overwritten or deleted objects cannot be recovered."


# ----------------------------------------------------------------------- Cloud SQL


def _sql_ip_configuration(resource: Resource) -> dict[str, Any]:
    return dig(resource.attributes, "settings", "ip_configuration")


def _sql_open_to_world(resource: Resource) -> str | None:
    for network in all_blocks(_sql_ip_configuration(resource), "authorized_networks"):
        if literal_str(network.get("value")) in ANY_ADDRESS:
            return "Authorized networks include 0.0.0.0/0: the database accepts any IP address."
    return None


def _sql_public_ip(resource: Resource) -> str | None:
    if as_bool(_sql_ip_configuration(resource).get("ipv4_enabled")) is False:
        return None
    return "The instance has a public IP address (ipv4_enabled is not false)."


def _sql_no_ssl(resource: Resource) -> str | None:
    ip_configuration = _sql_ip_configuration(resource)
    ssl_mode = literal_str(ip_configuration.get("ssl_mode"))
    if ssl_mode in ("ENCRYPTED_ONLY", "TRUSTED_CLIENT_CERTIFICATE_REQUIRED"):
        return None
    if as_bool(ip_configuration.get("require_ssl")) is True:
        return None
    return "Encrypted (SSL/TLS) connections are not required."


def _sql_no_backups(resource: Resource) -> str | None:
    backup = dig(resource.attributes, "settings", "backup_configuration")
    if as_bool(backup.get("enabled")) is True:
        return None
    return "Automated backups are not enabled."


def _sql_no_deletion_protection(resource: Resource) -> str | None:
    if as_bool(resource.attributes.get("deletion_protection")) is False:
        return "Deletion protection is switched off."
    return None


# ------------------------------------------------------------------ Compute Engine


def _fw_admin_ports_open(resource: Resource) -> str | None:
    opened = _open_ports(resource, ADMIN_PORTS)
    if not opened:
        return None
    return f"Firewall allows {', '.join(opened)} from 0.0.0.0/0 (the whole internet)."


def _fw_database_ports_open(resource: Resource) -> str | None:
    opened = _open_ports(resource, DATABASE_PORTS)
    if not opened:
        return None
    return f"Firewall allows database ports from 0.0.0.0/0: {', '.join(opened)}."


def _vm_default_sa_full_scope(resource: Resource) -> str | None:
    service_account = first_block(resource.attributes, "service_account")
    if not service_account:
        return None
    if _uses_default_sa_with_full_scope(service_account, service_account.get("scopes")):
        return "The VM runs as the default service account with the cloud-platform scope."
    return None


def _vm_public_ip(resource: Resource) -> str | None:
    for interface in all_blocks(resource.attributes, "network_interface"):
        if "access_config" in interface:
            return "The VM has an external (public) IP address."
    return None


# ----------------------------------------------------------------------- Cloud Run


def _run_public_invoker(resource: Resource) -> str | None:
    attributes = resource.attributes
    if literal_str(attributes.get("role")) != "roles/run.invoker":
        return None
    public = _public_members(attributes)
    if not public:
        return None
    return f"The service can be invoked by {', '.join(sorted(public))} without authentication."


def _run_containers(resource: Resource) -> list[dict[str, Any]]:
    template = first_block(resource.attributes, "template")
    containers = all_blocks(template, "containers")  # v2 layout
    containers += all_blocks(first_block(template, "spec"), "containers")  # v1 layout
    return containers


def _run_plaintext_secret(resource: Resource) -> str | None:
    names: list[str] = []
    for container in _run_containers(resource):
        for env in all_blocks(container, "env"):
            name = literal_str(env.get("name")) or ""
            if SECRET_NAME.search(name) and literal_str(env.get("value")):
                names.append(name)
    if not names:
        return None
    return f"Secret-looking values are set as plain environment variables: {', '.join(names)}."


# ----------------------------------------------------------------------------- GKE


def _gke_control_plane_open(resource: Resource) -> str | None:
    attributes = resource.attributes
    networks = first_block(attributes, "master_authorized_networks_config")
    for cidr in all_blocks(networks, "cidr_blocks"):
        if literal_str(cidr.get("cidr_block")) in ANY_ADDRESS:
            return "Control plane authorized networks include 0.0.0.0/0."
    private = first_block(attributes, "private_cluster_config")
    if "master_authorized_networks_config" in attributes:
        return None
    if as_bool(private.get("enable_private_endpoint")) is True:
        return None
    return "The control plane endpoint is public and has no authorized networks."


def _gke_public_nodes(resource: Resource) -> str | None:
    private = first_block(resource.attributes, "private_cluster_config")
    if as_bool(private.get("enable_private_nodes")) is True:
        return None
    return "Nodes are not private: each node gets a public IP address."


def _gke_legacy_abac(resource: Resource) -> str | None:
    if as_bool(resource.attributes.get("enable_legacy_abac")) is True:
        return "Legacy ABAC authorization is enabled."
    return None


def _gke_no_workload_identity(resource: Resource) -> str | None:
    attributes = resource.attributes
    if as_bool(attributes.get("enable_autopilot")) is True:
        return None  # Autopilot always uses Workload Identity
    if "workload_identity_config" in attributes:
        return None
    return "Workload Identity is not configured."


def _gke_nodes_default_sa(resource: Resource) -> str | None:
    node_config = first_block(resource.attributes, "node_config")
    if not node_config:
        return None
    if _uses_default_sa_with_full_scope(node_config, node_config.get("oauth_scopes")):
        return "Nodes run as the default service account with the cloud-platform scope."
    return None


# ------------------------------------------------------------------------ registry

_GCS = "https://cloud.google.com/storage/docs"
_SQL = "https://cloud.google.com/sql/docs/mysql"
_GKE = "https://cloud.google.com/kubernetes-engine/docs"
_RUN_IAM = (
    "google_cloud_run_service_iam_member",
    "google_cloud_run_service_iam_binding",
    "google_cloud_run_v2_service_iam_member",
    "google_cloud_run_v2_service_iam_binding",
)
_RUN_SERVICES = ("google_cloud_run_service", "google_cloud_run_v2_service")
_GCS_ACCESS = (
    "google_storage_bucket_iam_member",
    "google_storage_bucket_iam_binding",
    "google_storage_bucket_access_control",
    "google_storage_bucket_acl",
)

RULES: tuple[Rule, ...] = (
    Rule(
        "GCS-001",
        Severity.CRITICAL,
        _GCS_ACCESS,
        "Bucket is public",
        "Remove allUsers/allAuthenticatedUsers and grant access to specific identities. "
        "Use signed URLs or a load balancer with Cloud CDN for public content.",
        f"{_GCS}/public-access-prevention",
        _gcs_public_iam,
    ),
    Rule(
        "GCS-002",
        Severity.MEDIUM,
        ("google_storage_bucket",),
        "Uniform bucket-level access is off",
        "Set uniform_bucket_level_access = true so access is controlled by IAM only.",
        f"{_GCS}/uniform-bucket-level-access",
        _gcs_no_uniform_access,
    ),
    Rule(
        "GCS-003",
        Severity.MEDIUM,
        ("google_storage_bucket",),
        "Public access prevention is not enforced",
        'Set public_access_prevention = "enforced" unless the bucket must be public.',
        f"{_GCS}/public-access-prevention",
        _gcs_no_public_access_prevention,
    ),
    Rule(
        "GCS-004",
        Severity.LOW,
        ("google_storage_bucket",),
        "Object versioning is off",
        "Enable versioning (with a lifecycle rule to expire old versions) for important data.",
        f"{_GCS}/object-versioning",
        _gcs_no_versioning,
    ),
    Rule(
        "SQL-001",
        Severity.CRITICAL,
        ("google_sql_database_instance",),
        "Database is open to the whole internet",
        "Remove 0.0.0.0/0 from authorized_networks. Use private IP or the Cloud SQL Auth Proxy.",
        f"{_SQL}/authorize-networks",
        _sql_open_to_world,
    ),
    Rule(
        "SQL-002",
        Severity.HIGH,
        ("google_sql_database_instance",),
        "Database has a public IP",
        "Set ipv4_enabled = false and connect over private IP (private_network).",
        f"{_SQL}/private-ip",
        _sql_public_ip,
    ),
    Rule(
        "SQL-003",
        Severity.MEDIUM,
        ("google_sql_database_instance",),
        "SSL/TLS is not required",
        'Set ssl_mode = "ENCRYPTED_ONLY" (or stricter) in ip_configuration.',
        f"{_SQL}/configure-ssl-instance",
        _sql_no_ssl,
    ),
    Rule(
        "SQL-004",
        Severity.MEDIUM,
        ("google_sql_database_instance",),
        "Automated backups are off",
        "Enable backup_configuration (and point-in-time recovery for production data).",
        f"{_SQL}/backup-recovery/backups",
        _sql_no_backups,
    ),
    Rule(
        "SQL-005",
        Severity.LOW,
        ("google_sql_database_instance",),
        "Deletion protection is off",
        "Set deletion_protection = true for any instance that holds real data.",
        f"{_SQL}/deletion-protection",
        _sql_no_deletion_protection,
    ),
    Rule(
        "GCE-001",
        Severity.CRITICAL,
        ("google_compute_firewall",),
        "SSH/RDP is open to the whole internet",
        "Restrict source_ranges to known addresses, or use IAP TCP forwarding "
        "(35.235.240.0/20) instead of exposing SSH/RDP.",
        "https://cloud.google.com/iap/docs/using-tcp-forwarding",
        _fw_admin_ports_open,
    ),
    Rule(
        "GCE-002",
        Severity.HIGH,
        ("google_compute_firewall",),
        "Database ports are open to the whole internet",
        "Restrict source_ranges to the application subnet or use target tags/service accounts.",
        "https://cloud.google.com/firewall/docs/firewalls",
        _fw_database_ports_open,
    ),
    Rule(
        "GCE-003",
        Severity.HIGH,
        ("google_compute_instance",),
        "Default service account with full API access",
        "Create a dedicated service account with only the roles the VM needs.",
        "https://cloud.google.com/compute/docs/access/service-accounts",
        _vm_default_sa_full_scope,
    ),
    Rule(
        "GCE-004",
        Severity.MEDIUM,
        ("google_compute_instance",),
        "VM has a public IP",
        "Remove access_config and use Cloud NAT for outbound traffic and IAP or a load "
        "balancer for inbound traffic.",
        "https://cloud.google.com/compute/docs/ip-addresses",
        _vm_public_ip,
    ),
    Rule(
        "RUN-001",
        Severity.HIGH,
        _RUN_IAM,
        "Cloud Run service is publicly invokable",
        "If the service is not a public website or API, remove allUsers and grant "
        "roles/run.invoker to specific identities.",
        "https://cloud.google.com/run/docs/authenticating/public",
        _run_public_invoker,
    ),
    Rule(
        "RUN-002",
        Severity.HIGH,
        _RUN_SERVICES,
        "Secrets in plain environment variables",
        "Store the value in Secret Manager and reference it with value_source/secret_key_ref.",
        "https://cloud.google.com/run/docs/configuring/services/secrets",
        _run_plaintext_secret,
    ),
    Rule(
        "GKE-001",
        Severity.HIGH,
        ("google_container_cluster",),
        "GKE control plane is reachable from the internet",
        "Add master_authorized_networks_config with your own CIDR ranges, or enable the "
        "private endpoint.",
        f"{_GKE}/concepts/network-isolation",
        _gke_control_plane_open,
    ),
    Rule(
        "GKE-002",
        Severity.MEDIUM,
        ("google_container_cluster",),
        "GKE nodes have public IPs",
        "Set private_cluster_config.enable_private_nodes = true and use Cloud NAT for egress.",
        f"{_GKE}/concepts/network-isolation",
        _gke_public_nodes,
    ),
    Rule(
        "GKE-003",
        Severity.HIGH,
        ("google_container_cluster",),
        "Legacy ABAC is enabled",
        "Set enable_legacy_abac = false and use Kubernetes RBAC.",
        f"{_GKE}/how-to/hardening-your-cluster",
        _gke_legacy_abac,
    ),
    Rule(
        "GKE-004",
        Severity.MEDIUM,
        ("google_container_cluster",),
        "Workload Identity is not configured",
        "Add workload_identity_config so pods use their own IAM identity instead of the "
        "node service account.",
        f"{_GKE}/concepts/workload-identity",
        _gke_no_workload_identity,
    ),
    Rule(
        "GKE-005",
        Severity.HIGH,
        ("google_container_cluster", "google_container_node_pool"),
        "GKE nodes use the default service account with full API access",
        "Create a minimal node service account and set it in node_config.service_account.",
        f"{_GKE}/how-to/hardening-your-cluster",
        _gke_nodes_default_sa,
    ),
)


def check_security(resources: list[Resource]) -> list[Finding]:
    """Run every rule against every matching resource. Same input, same output, always."""
    findings: list[Finding] = []
    for resource in resources:
        for rule in RULES:
            if resource.type not in rule.resource_types:
                continue
            issue = rule.check(resource)
            if issue:
                findings.append(_to_finding(rule, resource, issue))
    return findings


def _to_finding(rule: Rule, resource: Resource, issue: str) -> Finding:
    return Finding(
        severity=rule.severity,
        resource=resource.address,
        issue=f"{rule.title}. {issue}",
        recommendation=rule.recommendation,
        source_url=rule.source_url,
        rule_id=rule.id,
        category=Category.SECURITY,
    )
