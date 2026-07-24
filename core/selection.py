"""Draft selection — the priority ladder from the LOOP spec (Loop 1).

Priority (high -> low):
  1. A draft whose precise `Scheduled Date` matches this slot (today).
  2. A `Scheduled` draft, choosing the Article with the fewest posts today
     (round-robin), respecting each article's `Target Posts Per Day`.
  3. A `Draft`-status draft, by `Argument #` ascending.
  4. Nothing eligible -> caller skips and logs.

Pure functions over `core.models.Draft` — no Notion/X imports.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Callable, Iterable, Optional

from core.models import Article, Draft
from core.timeutil import parse_notion_datetime, slot_to_minutes

# How close (minutes) a datetime-precise Scheduled Date must be to the slot.
SLOT_MATCH_TOLERANCE_MIN = 45


def make_eligibility(available_platforms: set) -> Callable[[Draft], bool]:
    """Eligibility check for the configured publishers: a draft qualifies if it
    targets at least one available platform (or has no platform set)."""
    def _eligible(draft: Draft) -> bool:
        return (not draft.platforms) or bool(set(draft.platforms) & available_platforms)
    return _eligible


def can_post_on_x(draft: Draft) -> bool:
    """Back-compat helper: eligibility when only the X publisher is configured."""
    return make_eligibility({"X"})(draft)


def _arg_key(draft: Draft) -> tuple:
    return (draft.argument_num if draft.argument_num is not None else math.inf, draft.title or "")


def matches_slot(
    draft: Draft,
    slot: str,
    ref: datetime,
    tzname: str = "Asia/Hong_Kong",
    tolerance_min: int = SLOT_MATCH_TOLERANCE_MIN,
) -> bool:
    """True if the draft's Scheduled Date falls on `ref`'s date and (for
    datetime-precise values) near `slot`. Date-only values match any slot today.
    """
    sd = draft.scheduled_date
    if not sd or not sd.get("start"):
        return False
    start = parse_notion_datetime(sd["start"], tzname)
    if start.date() != ref.date():
        return False
    if not sd.get("is_datetime"):
        return True
    start_min = start.hour * 60 + start.minute
    return abs(start_min - slot_to_minutes(slot)) <= tolerance_min


def _scheduled_sort_key(draft: Draft, tzname: str) -> tuple:
    sd = draft.scheduled_date or {}
    if sd.get("start"):
        try:
            return (0, parse_notion_datetime(sd["start"], tzname).timestamp(), *_arg_key(draft))
        except ValueError:
            pass
    return (1, 0.0, *_arg_key(draft))


def _pick_round_robin(
    drafts: list[Draft],
    posts_today_by_article: dict[str, int],
    articles_by_id: dict[str, Article],
) -> Optional[Draft]:
    """Among `Scheduled` drafts, prefer the article that is furthest from its
    daily target (fewest posts today, not yet over `Target Posts Per Day`)."""
    if not drafts:
        return None

    by_article: dict[Optional[str], list[Draft]] = {}
    for d in drafts:
        by_article.setdefault(d.article_id, []).append(d)

    def article_rank(article_id: Optional[str]) -> tuple:
        posted = posts_today_by_article.get(article_id, 0)
        art = articles_by_id.get(article_id) if article_id else None
        target = art.target_per_day if art and art.target_per_day else math.inf
        over_target = posted >= target
        # not over target first, then fewest posted, then deterministic by id
        return (over_target, posted, article_id or "")

    best_article = min(by_article.keys(), key=article_rank)
    return sorted(by_article[best_article], key=_arg_key)[0]


def select_draft(
    slot: str,
    ref: datetime,
    scheduled_drafts: Iterable[Draft],
    draft_drafts: Iterable[Draft],
    posts_today_by_article: dict[str, int],
    articles_by_id: dict[str, Article],
    *,
    tzname: str = "Asia/Hong_Kong",
    eligible: Callable[[Draft], bool] = can_post_on_x,
) -> tuple[Optional[Draft], str]:
    """Return (chosen_draft, reason). `chosen_draft` is None when nothing fits.

    `reason` is a short tag for the run log: "scheduled-slot", "round-robin",
    "argument-order" or "no-eligible-drafts".
    """
    scheduled = [d for d in scheduled_drafts if eligible(d)]
    drafts = [d for d in draft_drafts if eligible(d)]

    # 1. Precise Scheduled Date matching this slot (consider both pools).
    slot_matched = [d for d in (scheduled + drafts) if matches_slot(d, slot, ref, tzname)]
    if slot_matched:
        slot_matched.sort(key=lambda d: _scheduled_sort_key(d, tzname))
        return slot_matched[0], "scheduled-slot"

    # 2. Scheduled drafts, round-robin across articles.
    chosen = _pick_round_robin(scheduled, posts_today_by_article, articles_by_id)
    if chosen:
        return chosen, "round-robin"

    # 3. Draft-status drafts by Argument # ascending.
    if drafts:
        drafts.sort(key=_arg_key)
        return drafts[0], "argument-order"

    return None, "no-eligible-drafts"
