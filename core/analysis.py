"""Pure aggregation helpers for Loop 2 (LEARN).

No Notion/X imports — operates on plain DataPoint records so the maths can be
unit-tested. Engagement rate = (likes + replies + reposts) / impressions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class DataPoint:
    slot: Optional[str] = None
    content_type: Optional[str] = None
    hook: Optional[str] = None            # "A" / "B" / "C"
    impressions: float = 0.0
    likes: float = 0.0
    replies: float = 0.0
    reposts: float = 0.0
    link_clicks: float = 0.0

    @property
    def engagements(self) -> float:
        return self.likes + self.replies + self.reposts

    @property
    def engagement_rate(self) -> Optional[float]:
        if self.impressions and self.impressions > 0:
            return self.engagements / self.impressions
        return None


def engagement_rate(likes: float, replies: float, reposts: float, impressions: float) -> Optional[float]:
    if impressions and impressions > 0:
        return (likes + replies + reposts) / impressions
    return None


def _group_rates(points: list[DataPoint], key: Callable[[DataPoint], Optional[str]]) -> dict:
    """{group_value: {"n": count, "avg_rate": mean engagement rate}} for points
    that have both a group value and a computable engagement rate."""
    buckets: dict[str, list[float]] = {}
    for p in points:
        k = key(p)
        rate = p.engagement_rate
        if k is None or rate is None:
            continue
        buckets.setdefault(k, []).append(rate)
    return {k: {"n": len(v), "avg_rate": sum(v) / len(v)} for k, v in buckets.items()}


def ranked(points: list[DataPoint], key: Callable[[DataPoint], Optional[str]], min_n: int = 1) -> list[tuple[str, float, int]]:
    """List of (group, avg_rate, n) sorted by avg_rate desc, filtered to groups
    with at least `min_n` data points."""
    stats = _group_rates(points, key)
    rows = [(k, v["avg_rate"], v["n"]) for k, v in stats.items() if v["n"] >= min_n]
    return sorted(rows, key=lambda r: r[1], reverse=True)


def best_slots(points: list[DataPoint], top: int = 2, min_n: int = 1) -> list[str]:
    return [r[0] for r in ranked(points, lambda p: p.slot, min_n)[:top]]


def best_content_types(points: list[DataPoint], min_n: int = 1) -> list[str]:
    return [r[0] for r in ranked(points, lambda p: p.content_type, min_n)]


def best_hook(points: list[DataPoint], min_n: int = 1) -> Optional[str]:
    rows = ranked(points, lambda p: p.hook, min_n)
    return rows[0][0] if rows else None
