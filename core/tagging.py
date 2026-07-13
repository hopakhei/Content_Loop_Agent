"""Machine tags stamped on every Post Performance row (as JSON in `AI Notes`).

Tags are the experiment substrate for Loop 2: any dimension we want to A/B on
is a tag key, so a new experiment becomes a one-line change instead of a new
Notion property or a bumped "era" version. Pure and dependency-free so the
tag maths stays unit-testable.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import urlparse

# Bump ONLY when the composition LOGIC changes (how a draft becomes posts),
# so a tag filter can separate genuinely different compositions. This is the
# single source of truth for both the `comp` tag and the Performance
# `Loop Version` number.
COMPOSITION_VERSION = 4

_ISSUE_RE = re.compile(r"^#(\d+)-")


def domain_of(url: Optional[str]) -> Optional[str]:
    """Registrable-ish domain of a URL host (last two dot-labels, lowercased),
    enough to tell substack.com from github.com. None for blank/garbage."""
    if not url:
        return None
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return None
    labels = host.split(".")
    return ".".join(labels[-2:]) if len(labels) >= 2 else host


def series_of(title: Optional[str]) -> Optional[str]:
    """'1xx' / '2xx' … bucket from a draft title like '#201-04 …' (1xx =
    analysis-framework series, 2xx = build-in-public). None if no match."""
    m = _ISSUE_RE.match(title or "")
    return f"{m.group(1)[0]}xx" if m else None


def len_bucket(text: str) -> str:
    """Coarse length band of the root post."""
    n = len(text or "")
    if n <= 140:
        return "short"
    if n <= 280:
        return "mid"
    return "long"


def build_tags(
    *,
    platform: str,
    hook: Optional[str],
    posts: list[str],
    cta_url: Optional[str],
    cta_present: bool,
    title: Optional[str],
    extra: Optional[dict] = None,
) -> dict:
    """Assemble the tags dict recorded on a Performance row at post time.
    Keys whose value is None are dropped so a missing tag reads as 'unknown'
    (never as False) downstream."""
    tags = {
        "platform": platform,
        "hook": hook,
        "has_link": bool(cta_present),
        "link_domain": domain_of(cta_url) if cta_present else None,
        "chain_len": len(posts),
        "series": series_of(title),
        "len_bucket": len_bucket(posts[0]) if posts else "short",
        "comp": COMPOSITION_VERSION,
    }
    if extra:
        tags.update(extra)
    return {k: v for k, v in tags.items() if v is not None}
