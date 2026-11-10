"""Terraform parsing: text in, a list of `Resource` objects out. Pure code, no LLM.

Two steps, both deterministic:

1. `validate_terraform_input` rejects input that is empty, too large or clearly not
   Terraform. It runs before the graph starts, so bad input never reaches the LLM.
2. `parse_terraform` turns valid HCL into `Resource` objects. Comments are dropped here,
   which is the first line of defence against prompt injection hidden in comments.
"""

from __future__ import annotations

import re
from typing import Any

import hcl2
from hcl2 import SerializationOptions

from tools.models import Resource, Service

MAX_INPUT_BYTES = 200_000  # 200 KB, from CLAUDE.md "Rules"

# Resource types we know how to review, grouped by service.
SUPPORTED_TYPES: dict[str, Service] = {
    # Cloud Run
    "google_cloud_run_service": Service.CLOUD_RUN,
    "google_cloud_run_v2_service": Service.CLOUD_RUN,
    "google_cloud_run_service_iam_member": Service.CLOUD_RUN,
    "google_cloud_run_service_iam_binding": Service.CLOUD_RUN,
    "google_cloud_run_v2_service_iam_member": Service.CLOUD_RUN,
    "google_cloud_run_v2_service_iam_binding": Service.CLOUD_RUN,
    # Compute Engine
    "google_compute_instance": Service.COMPUTE,
    "google_compute_disk": Service.COMPUTE,
    "google_compute_firewall": Service.COMPUTE,
    "google_compute_network": Service.COMPUTE,
    "google_compute_subnetwork": Service.COMPUTE,
    # Cloud SQL
    "google_sql_database_instance": Service.CLOUD_SQL,
    "google_sql_database": Service.CLOUD_SQL,
    "google_sql_user": Service.CLOUD_SQL,
    # Cloud Storage
    "google_storage_bucket": Service.CLOUD_STORAGE,
    "google_storage_bucket_iam_member": Service.CLOUD_STORAGE,
    "google_storage_bucket_iam_binding": Service.CLOUD_STORAGE,
    "google_storage_bucket_access_control": Service.CLOUD_STORAGE,
    "google_storage_bucket_acl": Service.CLOUD_STORAGE,
    # GKE
    "google_container_cluster": Service.GKE,
    "google_container_node_pool": Service.GKE,
}

_TOP_LEVEL_BLOCK = re.compile(
    r"(?m)^\s*(resource|data|module|provider|variable|output|locals|terraform)\b[^\n{]*\{"
)
_PARSE_OPTIONS = SerializationOptions(with_comments=False, strip_string_quotes=True)
_INTERNAL_KEYS = ("__is_block__", "__comments__", "__inline_comments__")


class TerraformInputError(ValueError):
    """Base class: the input cannot be reviewed. The message is safe to show to users."""


class InputTooLargeError(TerraformInputError):
    pass


class NotTerraformError(TerraformInputError):
    pass


class TerraformParseError(TerraformInputError):
    pass


def validate_terraform_input(text: object) -> None:
    """Raise a `TerraformInputError` when the input should not be reviewed at all."""
    if not isinstance(text, str) or not text.strip():
        raise NotTerraformError("The input is empty. Paste the contents of a .tf file.")
    text = _strip_bom(text)
    size = len(text.encode("utf-8"))
    if size > MAX_INPUT_BYTES:
        raise InputTooLargeError(
            f"The input is {size / 1000:.0f} KB. The limit is {MAX_INPUT_BYTES // 1000} KB."
        )
    if "\x00" in text:
        raise NotTerraformError("The input looks like a binary file, not Terraform.")
    if not _TOP_LEVEL_BLOCK.search(text):
        raise NotTerraformError(
            "The input does not look like Terraform: no resource, provider, variable or "
            "module block was found. Only .tf files are supported."
        )


def parse_terraform(text: str) -> list[Resource]:
    """Parse Terraform text into resources. Unsupported types get `service=None`."""
    validate_terraform_input(text)
    text = _strip_bom(text)
    try:
        tree = hcl2.loads(text, serialization_options=_PARSE_OPTIONS)
    except Exception as exc:  # hcl2 raises several lark exception types
        raise TerraformParseError(_describe_syntax_error(exc)) from exc
    return list(_iter_resources(_clean(tree)))


def _strip_bom(text: str) -> str:
    """Drop the byte order mark that Windows editors put at the start of a file."""
    return text.lstrip("﻿")


def _iter_resources(tree: dict[str, Any]):
    for block in tree.get("resource", []):
        if not isinstance(block, dict):
            continue
        for resource_type, by_name in block.items():
            if not isinstance(by_name, dict):
                continue
            for name, attributes in by_name.items():
                yield Resource(
                    type=resource_type,
                    name=name,
                    service=SUPPORTED_TYPES.get(resource_type),
                    attributes=attributes if isinstance(attributes, dict) else {},
                )


def _clean(value: Any) -> Any:
    """Remove parser bookkeeping keys and stray quotes, recursively."""
    if isinstance(value, dict):
        return {
            _unquote(key): _clean(item) for key, item in value.items() if key not in _INTERNAL_KEYS
        }
    if isinstance(value, list):
        return [_clean(item) for item in value]
    if isinstance(value, str):
        return _unquote(value)
    return value


def _unquote(text: str) -> str:
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        return text[1:-1]
    return text


def _describe_syntax_error(exc: Exception) -> str:
    line = getattr(exc, "line", None)
    column = getattr(exc, "column", None)
    where = f" at line {line}, column {column}" if line and column else ""
    return f"Terraform syntax error{where}. Check for a missing brace or quote."
