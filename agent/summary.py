"""What the LLM is allowed to see of the Terraform file.

The LLM never receives the raw file. It receives a summary built here from a fixed list
of sizing attributes per resource type. Free-text fields (descriptions, labels,
metadata, environment variable values, comments) are not on the list, so text that an
attacker hides in them never reaches a prompt. Values that are on the list still have to
look like a plain identifier or number, or they are replaced with "<omitted>".

This is the second layer of the prompt-injection defence. The first is that comments are
dropped by the parser. The third is that security findings are produced by code and the
LLM has no way to change them.
"""

from __future__ import annotations

import re
from typing import Any

from tools.models import Resource
from tools.tf_values import first_block

OMITTED = "<omitted>"
_SAFE_VALUE = re.compile(r"^[A-Za-z0-9_./:\-]{1,60}$")

# Attribute paths that describe size, placement or billing. Nothing else is sent.
SIZING_FACTS: dict[str, tuple[tuple[str, ...], ...]] = {
    "google_compute_instance": (
        ("machine_type",),
        ("zone",),
        ("count",),
        ("boot_disk", "initialize_params", "size"),
        ("boot_disk", "initialize_params", "type"),
        ("scheduling", "preemptible"),
        ("scheduling", "provisioning_model"),
    ),
    "google_compute_disk": (("size",), ("type",), ("zone",)),
    "google_sql_database_instance": (
        ("database_version",),
        ("region",),
        ("settings", "tier"),
        ("settings", "edition"),
        ("settings", "availability_type"),
        ("settings", "disk_size"),
        ("settings", "disk_type"),
    ),
    "google_storage_bucket": (("location",), ("storage_class",)),
    "google_cloud_run_v2_service": (
        ("location",),
        ("template", "scaling", "min_instance_count"),
        ("template", "scaling", "max_instance_count"),
        ("template", "containers", "resources", "limits"),
        ("template", "containers", "resources", "cpu_idle"),
    ),
    "google_cloud_run_service": (("location",),),
    "google_container_cluster": (
        ("location",),
        ("enable_autopilot",),
        ("initial_node_count",),
        ("remove_default_node_pool",),
        ("node_config", "machine_type"),
        ("node_config", "disk_size_gb"),
        ("node_config", "disk_type"),
        ("node_config", "spot"),
    ),
    "google_container_node_pool": (
        ("node_count",),
        ("node_config", "machine_type"),
        ("node_config", "disk_size_gb"),
        ("node_config", "spot"),
        ("autoscaling", "min_node_count"),
        ("autoscaling", "max_node_count"),
    ),
}
# Blocks whose presence alone is a useful fact.
PRESENCE_FACTS: dict[str, tuple[str, ...]] = {
    "google_storage_bucket": ("lifecycle_rule", "autoclass", "versioning"),
    "google_container_node_pool": ("autoscaling",),
    "google_container_cluster": ("cluster_autoscaling",),
}


def summarize_resources(resources: list[Resource]) -> list[dict[str, Any]]:
    """Return the LLM-safe view of the supported resources."""
    return [_summarize(resource) for resource in resources if resource.supported]


def _summarize(resource: Resource) -> dict[str, Any]:
    facts: dict[str, Any] = {}
    for path in SIZING_FACTS.get(resource.type, ()):
        value = _read(resource.attributes, path)
        if value is not None:
            facts[".".join(path)] = _sanitize(value)
    for block in PRESENCE_FACTS.get(resource.type, ()):
        facts[f"has_{block}"] = block in resource.attributes
    return {"resource": resource.address, "service": resource.service, "facts": facts}


def _read(attributes: dict[str, Any], path: tuple[str, ...]) -> Any:
    current = attributes
    for key in path[:-1]:
        current = first_block(current, key)
    return current.get(path[-1])


def _sanitize(value: Any) -> Any:
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return value if _SAFE_VALUE.match(value) else OMITTED
    if isinstance(value, dict):
        return {
            str(key): _sanitize(item)
            for key, item in value.items()
            if _SAFE_VALUE.match(str(key)) and not isinstance(item, dict | list)
        }
    return OMITTED


def wrap_data(payload: str) -> str:
    """Mark the payload as data, so the prompt can tell the model to treat it that way."""
    return f"<review_data>\n{payload}\n</review_data>"
