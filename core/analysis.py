"""Pure aggregation helpers for Loop 2 (LEARN).

No Notion/X imports — operates on plain DataPoint records so the maths can be
unit-tested. Engagement rate = (likes + replies + reposts) / impressions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

# Follower-growth proxy weights (X). Conversation + profile visits drive
# follows; bookmarks signal reference value. Tunable priors.
GROWTH_WEIGHTS = {"replies": 3.0, "reposts": 2.0, "bookmarks": 2.0, "quotes": 1.0, "profile_clicks": 4.0}


@dataclass
class DataPoint:
    slot: Optional[str] = None
    content_type: Optional[str] = None
    hook: Optional[str] = None            # "A" / "B" / "C"
    platform: Optional[str] = None        # "X" / "Threads"
    composition: Optional[str] = None     # "v1" / "v2" (Loop Version on the row)
    impressions: float = 0.0
    likes: float = 0.0
    replies: float = 0.0
    reposts: float = 0.0
    link_clicks: float = 0.0
    bookmarks: float = 0.0
    quotes: float = 0.0
    profile_clicks: float = 0.0
    tags: dict = field(default_factory=dict)   # machine tags (core.tagging)

    @property
    def engagements(self) -> float:
        return self.likes + self.replies + self.reposts

    @property
    def engagement_rate(self) -> Optional[float]:
        if self.impressions and self.impressions > 0:
            return self.engagements / self.impressions
        return None

    @property
    def growth_rate(self) -> Optional[float]:
        """Follower-growth proxy per impression (X). None without impressions."""
        if not (self.impressions and self.impressions > 0):
            return None
        score = (
            GROWTH_WEIGHTS["replies"] * self.replies
            + GROWTH_WEIGHTS["reposts"] * self.reposts
            + GROWTH_WEIGHTS["bookmarks"] * self.bookmarks
            + GROWTH_WEIGHTS["quotes"] * self.quotes
            + GROWTH_WEIGHTS["profile_clicks"] * self.profile_clicks
        )
        return score / self.impressions


def engagement_rate(likes: float, replies: float, reposts: float, impressions: float) -> Optional[float]:
    if impressions and impressions > 0:
        return (likes + replies + reposts) / impressions
    return None


Metric = Callable[[DataPoint], Optional[float]]


def _by_engagement(p: DataPoint) -> Optional[float]:
    return p.engagement_rate


def _group_rates(points, key, metric: Metric = _by_engagement) -> dict:
    """{group_value: {"n": count, "avg_rate": mean metric}} for points that have
    both a group value and a computable metric."""
    buckets: dict[str, list[float]] = {}
    for p in points:
        k = key(p)
        rate = metric(p)
        if k is None or rate is None:
            continue
        buckets.setdefault(k, []).append(rate)
    return {k: {"n": len(v), "avg_rate": sum(v) / len(v)} for k, v in buckets.items()}


def ranked(points, key, min_n: int = 1, metric: Metric = _by_engagement) -> list[tuple[str, float, int]]:
    """List of (group, avg_metric, n) sorted desc, filtered to groups with at
    least `min_n` data points. `metric` defaults to engagement rate."""
    stats = _group_rates(points, key, metric)
    rows = [(k, v["avg_rate"], v["n"]) for k, v in stats.items() if v["n"] >= min_n]
    return sorted(rows, key=lambda r: r[1], reverse=True)


def ranked_by_tag(points, tag: str, min_n: int = 1, platform: Optional[str] = None,
                  metric: Metric = _by_engagement) -> list[tuple[str, float, int]]:
    """Rank the values of a machine tag. Points MISSING the tag are excluded
    (unknown ≠ any value). Optionally restrict to one platform first."""
    pool = [p for p in points if platform is None or p.platform == platform]
    return ranked(pool, lambda p: p.tags.get(tag) if tag in p.tags else None, min_n, metric)


def best_slots(points: list[DataPoint], top: int = 2, min_n: int = 1) -> list[str]:
    return [r[0] for r in ranked(points, lambda p: p.slot, min_n)[:top]]


def best_content_types(points: list[DataPoint], min_n: int = 1) -> list[str]:
    return [r[0] for r in ranked(points, lambda p: p.content_type, min_n)]


def best_hook(points: list[DataPoint], min_n: int = 1, metric: Metric = _by_engagement) -> Optional[str]:
    rows = ranked(points, lambda p: p.hook, min_n, metric)
    return rows[0][0] if rows else None
