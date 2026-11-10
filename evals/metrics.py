"""Metric calculations. Pure functions over plain data, so they are easy to test.

Every number in the README is produced by one of these functions from a saved run.
"""

from __future__ import annotations

import math
import statistics
from collections.abc import Iterable

from pydantic import BaseModel

Pair = tuple[str, str]  # (resource address, rule id)


class Confusion(BaseModel):
    """Counts for one or more samples."""

    true_positives: int = 0
    false_positives: int = 0
    false_negatives: int = 0

    def __add__(self, other: Confusion) -> Confusion:
        return Confusion(
            true_positives=self.true_positives + other.true_positives,
            false_positives=self.false_positives + other.false_positives,
            false_negatives=self.false_negatives + other.false_negatives,
        )

    @property
    def precision(self) -> float:
        found = self.true_positives + self.false_positives
        return self.true_positives / found if found else 1.0

    @property
    def recall(self) -> float:
        expected = self.true_positives + self.false_negatives
        return self.true_positives / expected if expected else 1.0

    @property
    def f1(self) -> float:
        total = self.precision + self.recall
        return 2 * self.precision * self.recall / total if total else 0.0

    def scores(self) -> dict[str, float | int]:
        return {
            **self.model_dump(),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
        }


def confusion(expected: Iterable[Pair], found: Iterable[Pair]) -> Confusion:
    """Compare the expected and found (resource, rule) pairs of one sample."""
    expected_set, found_set = set(expected), set(found)
    return Confusion(
        true_positives=len(expected_set & found_set),
        false_positives=len(found_set - expected_set),
        false_negatives=len(expected_set - found_set),
    )


def percentile(values: list[float], percent: float) -> float:
    """Nearest-rank percentile (p95 of 20 values is the 19th smallest)."""
    if not values:
        raise ValueError("percentile of an empty list")
    ordered = sorted(values)
    rank = max(1, math.ceil(percent / 100 * len(ordered)))
    return ordered[rank - 1]


def latency_stats(seconds: list[float]) -> dict[str, float | int]:
    return {
        "n": len(seconds),
        "median_s": round(statistics.median(seconds), 6),
        "p95_s": round(percentile(seconds, 95), 6),
        "mean_s": round(statistics.fmean(seconds), 6),
    }


def cost_errors(expected: list[float], estimated: list[float]) -> dict[str, float | int]:
    """Absolute and relative error of the cost estimates against hand-calculated values."""
    absolute = [abs(e - a) for e, a in zip(expected, estimated, strict=True)]
    relative = [abs(e - a) / e for e, a in zip(expected, estimated, strict=True) if e > 0]
    return {
        "n": len(absolute),
        "mean_abs_error_usd": round(statistics.fmean(absolute), 4),
        "max_abs_error_usd": round(max(absolute), 4),
        "mean_abs_pct_error": round(100 * statistics.fmean(relative), 4) if relative else 0.0,
    }


def hit_rate(ranks: list[int | None], k: int) -> float:
    """Share of queries whose expected document is in the top `k` (rank is 1-based)."""
    return round(sum(1 for rank in ranks if rank is not None and rank <= k) / len(ranks), 4)


def mean_reciprocal_rank(ranks: list[int | None]) -> float:
    return round(statistics.fmean(1 / rank if rank else 0.0 for rank in ranks), 4)


def share(part: int, whole: int) -> float | None:
    """`part / whole`, or None when there is nothing to take a share of."""
    return round(part / whole, 4) if whole else None


def mean_or_none(values: Iterable[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return round(statistics.fmean(present), 6) if present else None
