"""Small helpers for reading values out of parsed Terraform attributes.

Terraform values can be literals (`"e2-medium"`, `2`, `true`) or expressions that are only
known at apply time (`var.region`, `google_storage_bucket.b.name`). We never evaluate
expressions. A value we cannot read is treated as "unknown", and each rule decides what
unknown means for it.
"""

from __future__ import annotations

from typing import Any


def is_reference(value: Any) -> bool:
    """True when the value is an unresolved Terraform expression such as `${var.x}`."""
    return isinstance(value, str) and "${" in value


def literal_str(value: Any) -> str | None:
    """Return the value as a plain string, or None when it is missing or an expression."""
    if isinstance(value, str) and not is_reference(value):
        return value
    return None


def literal_number(value: Any) -> float | None:
    """Return a number for `2`, `2.5` or `"2"`. None for anything else."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str) and not is_reference(value):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def as_bool(value: Any) -> bool | None:
    """Return True/False for a literal boolean, None when missing or an expression."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str) and value.lower() in ("true", "false"):
        return value.lower() == "true"
    return None


def all_blocks(attributes: dict[str, Any], key: str) -> list[dict[str, Any]]:
    """Return every nested block called `key` (HCL allows a block to repeat)."""
    value = attributes.get(key)
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    return []


def first_block(attributes: dict[str, Any], key: str) -> dict[str, Any]:
    """Return the first nested block called `key`, or an empty dict."""
    blocks = all_blocks(attributes, key)
    return blocks[0] if blocks else {}


def dig(attributes: dict[str, Any], *path: str) -> dict[str, Any]:
    """Walk nested blocks: `dig(a, "settings", "ip_configuration")`."""
    current = attributes
    for key in path:
        current = first_block(current, key)
    return current


def string_list(value: Any) -> list[str]:
    """Return the literal strings in a list attribute (expressions are dropped)."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and not is_reference(item)]
