"""Loop 2 — LEARN.

讀數據 → 分析 → 更新規則.

Runs nightly (02:00 HKT). Refreshes engagement metrics for posts older than 24h,
aggregates engagement rate by slot / content type / hook over the last 30 days,
and (when there are enough data points) updates the Posting Rules that Loop 1 reads.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from config import settings
from config.schema import Performance, PostingRules
from core.analysis import DataPoint, best_content_types, best_hook, best_slots, ranked
from core.timeutil import nearest_slot, parse_notion_datetime
from services.notion import NotionService
from services.twitter import TwitterService

# Minimum data points before we trust an aggregate enough to rewrite the rules.
MIN_DATA_POINTS = 20
ANALYSIS_WINDOW_DAYS = 30


def run(
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None,
    notion: Optional[NotionService] = None,
    twitter: Optional[TwitterService] = None,
) -> dict:
    log = logger or logging.getLogger("loop.learn")
    notion = notion or NotionService(log)
    twitter = twitter or TwitterService(dry_run=dry_run, logger=log)

    log.info("Loop 2 LEARN | dry_run=%s | window=%dd", dry_run, ANALYSIS_WINDOW_DAYS)

    rows = notion.get_performance_rows(since_days=ANALYSIS_WINDOW_DAYS)
    log.info("Loaded %d performance rows.", len(rows))

    refreshed = _refresh_metrics(rows, notion, twitter, log, dry_run=dry_run)
    log.info("Refreshed metrics for %d posts.", refreshed)

    points = [_to_point(r) for r in rows]
    points = [p for p in points if p.engagement_rate is not None]
    log.info("Usable data points (with impressions): %d", len(points))

    slot_rank = ranked(points, lambda p: p.slot)
    type_rank = ranked(points, lambda p: p.content_type)
    hook_rank = ranked(points, lambda p: p.hook)
    _log_ranking(log, "Slot", slot_rank)
    _log_ranking(log, "Content Type", type_rank)
    _log_ranking(log, "Hook", hook_rank)

    summary = {
        "rows": len(rows),
        "data_points": len(points),
        "best_slots": best_slots(points, top=2),
        "best_content_types": best_content_types(points),
        "best_hook": best_hook(points),
        "rules_updated": False,
    }

    if len(points) < MIN_DATA_POINTS:
        log.info("Only %d/%d data points — not updating Posting Rules yet.", len(points), MIN_DATA_POINTS)
        return summary

    notes = _build_notes(slot_rank, type_rank, hook_rank)
    if dry_run:
        log.info("[dry-run] would update Posting Rules: %s", summary)
        return summary

    fields = {
        PostingRules.BEST_SLOTS: {"rich_text": [{"text": {"content": json.dumps(summary["best_slots"], ensure_ascii=False)}}]},
        PostingRules.BEST_CONTENT_TYPES: {"rich_text": [{"text": {"content": json.dumps(summary["best_content_types"], ensure_ascii=False)}}]},
        PostingRules.DAILY_LIMIT: {"number": settings.DAILY_HARD_LIMIT},
        PostingRules.UPDATED_AT: {"date": {"start": datetime.now(timezone.utc).isoformat()}},
        PostingRules.NOTES: {"rich_text": [{"text": {"content": notes[:1900]}}]},
    }
    if summary["best_hook"]:
        fields[PostingRules.BEST_HOOK_TYPE] = {"select": {"name": summary["best_hook"]}}

    page_id = notion.upsert_posting_rules("LOOP Auto Rules", fields)
    summary["rules_updated"] = page_id is not None
    log.info("Posting Rules %s.", "updated" if summary["rules_updated"] else "not written (DB unset)")
    return summary


def _refresh_metrics(rows, notion, twitter, log, *, dry_run: bool) -> int:
    """Pull fresh engagement for real (non dry-run) tweets older than 24h and
    write the numbers back to Notion. Mutates `rows` in place."""
    now = datetime.now(timezone.utc)
    by_id = {}
    for r in rows:
        pid = r.get("post_id") or ""
        if not pid or pid.startswith("DRYRUN-") or not r.get("posted_at"):
            continue
        posted = parse_notion_datetime(r["posted_at"], settings.TZ_NAME).astimezone(timezone.utc)
        if (now - posted).total_seconds() >= 24 * 3600:
            by_id[pid] = r

    if not by_id or dry_run:
        return 0

    metrics = twitter.get_metrics(list(by_id))
    updated = 0
    for pid, m in metrics.items():
        row = by_id.get(pid)
        if not row:
            continue
        row.update({
            "impressions": m.get("impressions", row["impressions"]),
            "likes": m.get("likes", row["likes"]),
            "replies": m.get("replies", row["replies"]),
            "reposts": m.get("reposts", row["reposts"]),
            "link_clicks": m.get("link_clicks", row["link_clicks"]),
        })
        notion.update_performance_metrics(row["page_id"], {
            Performance.IMPRESSIONS: row["impressions"],
            Performance.LIKES: row["likes"],
            Performance.REPLIES: row["replies"],
            Performance.REPOSTS: row["reposts"],
            Performance.LINK_CLICKS: row["link_clicks"],
        })
        updated += 1
    return updated


def _to_point(row: dict) -> DataPoint:
    slot = None
    if row.get("posted_at"):
        dt = parse_notion_datetime(row["posted_at"], settings.TZ_NAME)
        slot = nearest_slot(dt, settings.POST_SLOTS_HKT)
    hook = (row.get("hook_used") or "")[:1] or None  # "A - 反共識" -> "A"
    return DataPoint(
        slot=slot,
        content_type=row.get("content_type"),
        hook=hook,
        impressions=row.get("impressions", 0.0),
        likes=row.get("likes", 0.0),
        replies=row.get("replies", 0.0),
        reposts=row.get("reposts", 0.0),
        link_clicks=row.get("link_clicks", 0.0),
    )


def _log_ranking(log, label, rows) -> None:
    if not rows:
        log.info("%s ranking: (no data)", label)
        return
    pretty = ", ".join(f"{k}={rate:.2%}(n={n})" for k, rate, n in rows)
    log.info("%s ranking: %s", label, pretty)


def _build_notes(slot_rank, type_rank, hook_rank) -> str:
    def fmt(rows):
        return "; ".join(f"{k}: {rate:.2%} (n={n})" for k, rate, n in rows) or "n/a"
    return (
        f"Slots → {fmt(slot_rank)}\n"
        f"Content Types → {fmt(type_rank)}\n"
        f"Hooks → {fmt(hook_rank)}"
    )
