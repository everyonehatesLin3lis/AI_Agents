"""Monthly cost estimate for the supported resources. Pure code, no LLM.

The estimate is deliberately simple so every number can be checked by hand:

    monthly cost = quantity x unit price x 730 hours (or x GB for storage)

What it does NOT know: traffic, stored data volume, sustained/committed use discounts,
Spot prices, network egress. Each line lists the assumptions it made, and the report
shows them, so the reader knows how far to trust the number.
"""

from __future__ import annotations

import re
from typing import Any

from tools.models import CostEstimate, CostLine, Resource
from tools.pricing import PriceNotFoundError, PriceTable
from tools.tf_values import as_bool, dig, first_block, literal_number, literal_str, string_list

HOURS_PER_MONTH = 730
SECONDS_PER_MONTH = HOURS_PER_MONTH * 3600
DEFAULT_ASSUMED_STORAGE_GB = 100.0
ZONES_PER_REGION = 3

# Shared-core machine types: (billed vCPUs, memory GB).
SHARED_CORE: dict[str, tuple[float, float]] = {
    "e2-micro": (0.25, 1.0),
    "e2-small": (0.5, 2.0),
    "e2-medium": (1.0, 4.0),
}
# Memory per vCPU in GB for each (family, class).
GB_PER_VCPU: dict[tuple[str, str], float] = {
    ("e2", "standard"): 4.0,
    ("e2", "highmem"): 8.0,
    ("e2", "highcpu"): 1.0,
    ("n1", "standard"): 3.75,
    ("n1", "highmem"): 6.5,
    ("n1", "highcpu"): 0.9,
    ("n2", "standard"): 4.0,
    ("n2", "highmem"): 8.0,
    ("n2", "highcpu"): 1.0,
    ("n2d", "standard"): 4.0,
    ("n2d", "highmem"): 8.0,
    ("n2d", "highcpu"): 1.0,
}
_PREDEFINED = re.compile(r"^(e2|n1|n2|n2d)-(standard|highmem|highcpu)-(\d+)$")
_CUSTOM = re.compile(r"^(?:(e2|n1|n2|n2d)-)?custom-(\d+)-(\d+)$")
_SQL_CUSTOM = re.compile(r"^db-custom-(\d+)-(\d+)$")
_SQL_N1 = re.compile(r"^db-n1-(standard|highmem)-(\d+)$")
_ZONE = re.compile(r"^[a-z]+-[a-z]+\d+-[a-z]$")
_REGION = re.compile(r"^[a-z]+-[a-z]+\d+$")
_CLUSTER_REF = re.compile(r"google_container_cluster\.([A-Za-z0-9_-]+)")
_MEMORY_UNITS = {"Ki": 1 / 1024**2, "Mi": 1 / 1024, "Gi": 1.0, "M": 1 / 1024, "G": 1.0}


class UnpricedError(Exception):
    """This resource cannot be priced. The message becomes an assumption on its line."""


# ----------------------------------------------------------------------- public API


def estimate_cost(
    resources: list[Resource],
    region: str,
    prices: PriceTable,
    assumed_storage_gb: float = DEFAULT_ASSUMED_STORAGE_GB,
) -> CostEstimate:
    """Estimate the monthly cost of `resources`. `region` is used when a resource has none."""
    context = _Context(resources, region, prices, assumed_storage_gb)
    lines = [line for resource in resources if (line := _price_resource(resource, context))]
    notes = list(dict.fromkeys(context.notes))
    if prices.may_be_outdated:
        notes.insert(0, "Prices may be outdated: the static price table was used.")
    return CostEstimate(
        lines=lines,
        total_monthly_usd=round(sum(line.monthly_usd for line in lines), 2),
        default_region=region,
        regions_used=sorted(context.regions_used),
        price_source=prices.source,
        prices_may_be_outdated=prices.may_be_outdated,
        notes=notes,
    )


def machine_shape(machine_type: str) -> tuple[str, float, float]:
    """Return (family, vCPUs, memory GB) for a Compute Engine machine type."""
    if machine_type in SHARED_CORE:
        vcpus, memory_gb = SHARED_CORE[machine_type]
        return "e2", vcpus, memory_gb
    if match := _PREDEFINED.match(machine_type):
        family, machine_class, vcpus = match.group(1), match.group(2), int(match.group(3))
        return family, float(vcpus), vcpus * GB_PER_VCPU[(family, machine_class)]
    if match := _CUSTOM.match(machine_type):
        return match.group(1) or "n1", float(match.group(2)), int(match.group(3)) / 1024
    raise UnpricedError(f"Unknown machine type '{machine_type}': not priced.")


# ------------------------------------------------------------------------ internals


class _Context:
    """Everything a pricing function needs, so the functions stay small."""

    def __init__(
        self, resources: list[Resource], region: str, prices: PriceTable, storage_gb: float
    ) -> None:
        self.resources = resources
        self.default_region = region
        self.prices = prices
        self.assumed_storage_gb = storage_gb
        self.notes: list[str] = []
        self.regions_used: set[str] = set()

    def price(self, key: str, region: str) -> float:
        self.regions_used.add(region)
        if not self.prices.knows_region(region):
            self.notes.append(
                f"No prices for region '{region}': {self.prices.base_region} prices were used."
            )
        try:
            return self.prices.unit_price(key, region)
        except PriceNotFoundError as exc:
            raise UnpricedError(f"No price found for '{key}'.") from exc

    def machine_hour(self, machine_type: str, region: str) -> float:
        family, vcpus, memory_gb = machine_shape(machine_type)
        return vcpus * self.price(f"compute.{family}.vcpu_hour", region) + memory_gb * self.price(
            f"compute.{family}.ram_gb_hour", region
        )

    def disk_month(self, disk_type: str, size_gb: float, region: str) -> float:
        return size_gb * self.price(f"disk.{disk_type}.gb_month", region)


def _price_resource(resource: Resource, context: _Context) -> CostLine | None:
    pricer = _PRICERS.get(resource.type)
    if pricer is None or resource.service is None:
        return None
    assumptions: list[str] = []
    try:
        monthly = pricer(resource, context, assumptions)
        priced = True
    except UnpricedError as exc:
        monthly, priced = 0.0, False
        assumptions[:] = [str(exc)]  # drop half-built assumptions: nothing was priced
    count = _count(resource, assumptions)
    return CostLine(
        resource=resource.address,
        service=resource.service,
        monthly_usd=round(monthly * count, 2),
        priced=priced,
        assumptions=assumptions,
    )


def _count(resource: Resource, assumptions: list[str]) -> int:
    attributes = resource.attributes
    if "for_each" in attributes:
        assumptions.append("for_each is not evaluated: priced as one instance.")
        return 1
    if "count" not in attributes:
        return 1
    count = literal_number(attributes["count"])
    if count is None:
        assumptions.append("count is an expression: priced as one instance.")
        return 1
    assumptions.append(f"count = {int(count)}.")
    return int(count)


def _location(attributes: dict[str, Any], context: _Context, assumptions: list[str]) -> str:
    """Region for pricing: the resource's own region/zone/location, else the default."""
    for key in ("region", "zone", "location"):
        value = literal_str(attributes.get(key))
        if value and _ZONE.match(value):
            return value.rsplit("-", 1)[0]
        if value and _REGION.match(value):
            return value
    assumptions.append(f"Region not set as a literal: assumed {context.default_region}.")
    return context.default_region


def _zone_count(attributes: dict[str, Any]) -> int:
    """How many zones a GKE cluster or node pool spreads its nodes over."""
    node_locations = string_list(attributes.get("node_locations"))
    if node_locations:
        return len(node_locations)
    location = literal_str(attributes.get("location")) or ""
    return ZONES_PER_REGION if _REGION.match(location) else 1


# ---------------------------------------------------------------- Compute Engine


def _price_instance(resource: Resource, context: _Context, assumptions: list[str]) -> float:
    attributes = resource.attributes
    machine_type = literal_str(attributes.get("machine_type"))
    if not machine_type:
        raise UnpricedError("machine_type is not a literal value: not priced.")
    region = _location(attributes, context, assumptions)
    params = dig(attributes, "boot_disk", "initialize_params")
    disk_gb = literal_number(params.get("size")) or 10.0
    disk_type = literal_str(params.get("type")) or "pd-standard"
    if _is_spot(attributes):
        assumptions.append("Spot/preemptible VM priced at the on-demand rate (upper bound).")
    assumptions.append(f"{machine_type} running {HOURS_PER_MONTH} h/month in {region}.")
    assumptions.append(f"Boot disk {disk_gb:g} GB {disk_type}.")
    hourly = context.machine_hour(machine_type, region)
    return hourly * HOURS_PER_MONTH + context.disk_month(disk_type, disk_gb, region)


def _is_spot(attributes: dict[str, Any]) -> bool:
    scheduling = first_block(attributes, "scheduling")
    return (
        as_bool(scheduling.get("preemptible")) is True
        or literal_str(scheduling.get("provisioning_model")) == "SPOT"
    )


def _price_disk(resource: Resource, context: _Context, assumptions: list[str]) -> float:
    attributes = resource.attributes
    size_gb = literal_number(attributes.get("size"))
    if size_gb is None:
        raise UnpricedError("Disk size is not set as a literal: not priced.")
    disk_type = literal_str(attributes.get("type")) or "pd-standard"
    region = _location(attributes, context, assumptions)
    assumptions.append(f"{size_gb:g} GB {disk_type} in {region}.")
    return context.disk_month(disk_type, size_gb, region)


# --------------------------------------------------------------------- Cloud SQL


def _sql_instance_hour(tier: str, region: str, context: _Context) -> float:
    if tier in ("db-f1-micro", "db-g1-small"):
        return context.price(f"sql.{tier}.hour", region)
    if match := _SQL_CUSTOM.match(tier):
        vcpus, memory_gb = int(match.group(1)), int(match.group(2)) / 1024
    elif match := _SQL_N1.match(tier):
        vcpus = int(match.group(2))
        memory_gb = vcpus * (3.75 if match.group(1) == "standard" else 6.5)
    else:
        raise UnpricedError(f"Unknown Cloud SQL tier '{tier}': not priced.")
    return vcpus * context.price("sql.vcpu_hour", region) + memory_gb * context.price(
        "sql.ram_gb_hour", region
    )


def _price_sql(resource: Resource, context: _Context, assumptions: list[str]) -> float:
    attributes = resource.attributes
    settings = first_block(attributes, "settings")
    tier = literal_str(settings.get("tier"))
    if not tier:
        raise UnpricedError("settings.tier is not a literal value: not priced.")
    region = _location(attributes, context, assumptions)
    disk_gb = literal_number(settings.get("disk_size")) or 10.0
    disk_kind = "hdd" if literal_str(settings.get("disk_type")) == "PD_HDD" else "ssd"
    high_availability = literal_str(settings.get("availability_type")) == "REGIONAL"
    replicas = 2 if high_availability else 1
    assumptions.append(f"{tier} running {HOURS_PER_MONTH} h/month in {region}.")
    assumptions.append(f"Storage {disk_gb:g} GB {disk_kind.upper()}.")
    if high_availability:
        assumptions.append("High availability (REGIONAL) doubles instance and storage cost.")
    instance = _sql_instance_hour(tier, region, context) * HOURS_PER_MONTH
    storage = disk_gb * context.price(f"sql.storage.{disk_kind}.gb_month", region)
    return (instance + storage) * replicas


# ----------------------------------------------------------------- Cloud Storage


def _price_bucket(resource: Resource, context: _Context, assumptions: list[str]) -> float:
    attributes = resource.attributes
    storage_class = (literal_str(attributes.get("storage_class")) or "STANDARD").lower()
    location = (literal_str(attributes.get("location")) or "").lower()
    region = location if _REGION.match(location) else context.default_region
    if location and region != location:
        assumptions.append(
            f"Location '{location.upper()}' is a multi-region: priced as {region} (approximate)."
        )
    assumptions.append(
        f"Assumed {context.assumed_storage_gb:g} GB stored ({storage_class.upper()}). "
        "Terraform does not say how much data a bucket holds."
    )
    assumptions.append("Operations and network egress are not included.")
    return context.assumed_storage_gb * context.price(f"gcs.{storage_class}.gb_month", region)


# --------------------------------------------------------------------- Cloud Run


def _cpu_count(value: Any) -> float:
    text = str(value) if value is not None else "1"
    try:
        return float(text[:-1]) / 1000 if text.endswith("m") else float(text)
    except ValueError:
        return 1.0


def _memory_gib(value: Any) -> float:
    text = str(value) if value is not None else "512Mi"
    for unit, factor in _MEMORY_UNITS.items():
        if text.endswith(unit):
            try:
                return float(text[: -len(unit)]) * factor
            except ValueError:
                return 0.5
    return 0.5


def _run_shape(resource: Resource) -> tuple[float, float, float, bool]:
    """Return (min instances, vCPUs, memory GiB, cpu always allocated)."""
    template = first_block(resource.attributes, "template")
    if resource.type == "google_cloud_run_v2_service":
        container = first_block(template, "containers")
        resources = first_block(container, "resources")
        minimum = literal_number(first_block(template, "scaling").get("min_instance_count"))
        always_on = as_bool(resources.get("cpu_idle")) is False
    else:
        container = dig(template, "spec", "containers")
        resources = first_block(container, "resources")
        annotations = first_block(template, "metadata").get("annotations")
        annotations = annotations if isinstance(annotations, dict) else {}
        minimum = literal_number(annotations.get("autoscaling.knative.dev/minScale"))
        always_on = annotations.get("run.googleapis.com/cpu-throttling") == "false"
    limits = resources.get("limits")
    limits = limits if isinstance(limits, dict) else {}
    cpu, memory = _cpu_count(limits.get("cpu")), _memory_gib(limits.get("memory"))
    return minimum or 0.0, cpu, memory, always_on


def _price_run(resource: Resource, context: _Context, assumptions: list[str]) -> float:
    minimum, cpu, memory, always_on = _run_shape(resource)
    region = _location(resource.attributes, context, assumptions)
    assumptions.append("Request-based usage depends on traffic and is not included.")
    if minimum <= 0:
        assumptions.append("min instances = 0: no fixed monthly cost.")
        return 0.0
    mode = "always" if always_on else "idle"
    assumptions.append(
        f"{minimum:g} min instance(s) kept warm, {cpu:g} vCPU / {memory:g} GiB, "
        f"{'CPU always allocated' if always_on else 'idle rate'}."
    )
    per_second = cpu * context.price(f"run.vcpu_second_{mode}", region) + memory * context.price(
        f"run.ram_gib_second_{mode}", region
    )
    return minimum * per_second * SECONDS_PER_MONTH


# --------------------------------------------------------------------------- GKE


def _node_group_month(
    node_config: dict[str, Any], nodes: float, region: str, context: _Context, notes: list[str]
) -> float:
    machine_type = literal_str(node_config.get("machine_type")) or "e2-medium"
    disk_gb = literal_number(node_config.get("disk_size_gb")) or 100.0
    disk_type = literal_str(node_config.get("disk_type")) or "pd-balanced"
    notes.append(f"{nodes:g} node(s) of {machine_type} with {disk_gb:g} GB {disk_type} each.")
    per_node = context.machine_hour(machine_type, region) * HOURS_PER_MONTH
    return nodes * (per_node + context.disk_month(disk_type, disk_gb, region))


def _price_cluster(resource: Resource, context: _Context, assumptions: list[str]) -> float:
    attributes = resource.attributes
    region = _location(attributes, context, assumptions)
    fee = context.price("gke.cluster_fee_hour", region) * HOURS_PER_MONTH
    assumptions.append("Cluster management fee (the GKE free tier credit is not applied).")
    if as_bool(attributes.get("enable_autopilot")) is True:
        assumptions.append("Autopilot bills per pod request: workload cost is not included.")
        return fee
    if as_bool(attributes.get("remove_default_node_pool")) is True:
        return fee
    nodes = (literal_number(attributes.get("initial_node_count")) or 1.0) * _zone_count(attributes)
    node_config = first_block(attributes, "node_config")
    return fee + _node_group_month(node_config, nodes, region, context, assumptions)


def _cluster_of(node_pool: Resource, context: _Context) -> Resource | None:
    match = _CLUSTER_REF.search(str(node_pool.attributes.get("cluster", "")))
    if not match:
        return None
    for resource in context.resources:
        if resource.type == "google_container_cluster" and resource.name == match.group(1):
            return resource
    return None


def _price_node_pool(resource: Resource, context: _Context, assumptions: list[str]) -> float:
    attributes = dict(resource.attributes)
    cluster = _cluster_of(resource, context)
    if "location" not in attributes and cluster is not None:
        attributes["location"] = cluster.attributes.get("location")
    region = _location(attributes, context, assumptions)
    autoscaling = first_block(attributes, "autoscaling")
    per_zone = (
        literal_number(attributes.get("node_count"))
        or literal_number(attributes.get("initial_node_count"))
        or literal_number(autoscaling.get("min_node_count"))
        or 1.0
    )
    if autoscaling:
        assumptions.append("Autoscaling pool priced at its starting size.")
    nodes = per_zone * _zone_count(attributes)
    return _node_group_month(
        first_block(attributes, "node_config"), nodes, region, context, assumptions
    )


_PRICERS = {
    "google_compute_instance": _price_instance,
    "google_compute_disk": _price_disk,
    "google_sql_database_instance": _price_sql,
    "google_storage_bucket": _price_bucket,
    "google_cloud_run_service": _price_run,
    "google_cloud_run_v2_service": _price_run,
    "google_container_cluster": _price_cluster,
    "google_container_node_pool": _price_node_pool,
}
