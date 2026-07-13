"""Loop 2 — LEARN.

讀數據 → 分析 → 更新規則.

Runs nightly (02:00 HKT). Snapshots follower counts, refreshes each post's
metrics once (24–48h old), then ranks machine tags PER PLATFORM — X on a
follower-growth proxy, Threads on engagement — and writes the per-platform
winners into the Agent Rules that Loop 1 reads. See docs/eval-upgrade-plan.md.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from config import settings
from config.schema import Performance
from core.analysis import (
    DataPoint, best_content_types, best_hook, best_slots, ranked, ranked_by_tag,
)
from core.timeutil import nearest_slot, now as hkt_now, parse_notion_datetime
from services.notion import NotionService
from services.threads import ThreadsService
from services.twitter import TwitterService

# Minimum data points before we trust an aggregate enough to rewrite the rules.
MIN_DATA_POINTS = 20
# Minimum points in a single CELL (a slot / hook / type value, per platform)
# before that cell may set a written rule. Guards against a 3-post fluke
# defining behaviour.
MIN_CELL_N = 8
ANALYSIS_WINDOW_DAYS = 30
# Data points at which a learned rule reaches full (100) confidence.
FULL_CONFIDENCE_POINTS = 40
# Machine tags ranked per platform for the nightly report.
REPORT_TAGS = ("has_link", "link_domain", "chain_len", "series", "len_bucket")


def _growth(p: DataPoint) -> Optional[float]:
    return p.growth_rate
# Read each post's metrics EXACTLY ONCE, on the nightly run where its age
# falls in [24h, 48h) — engagement has matured by 24h, and with LEARN at
# 02:00 HKT every slot lands in this window on its second night. No re-reads:
# X reads consume the same monthly credit budget as writes, so a retry rule
# would leak quota every night for every post that never gets impressions.
REFRESH_MIN_AGE_HOURS = 24
REFRESH_MAX_AGE_HOURS = 48


def run(
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None,
    notion: Optional[NotionService] = None,
    twitter: Optional[TwitterService] = None,
    threads: Optional[ThreadsService] = None,
) -> dict:
    log = logger or logging.getLogger("loop.learn")
    notion = notion or NotionService(log)
    twitter = twitter or TwitterService(dry_run=dry_run, logger=log)
    if threads is None and settings.THREADS_ACCESS_TOKEN:
        threads = ThreadsService(dry_run=dry_run, logger=log)

    log.info("Loop 2 LEARN | dry_run=%s | window=%dd", dry_run, ANALYSIS_WINDOW_DAYS)

    follower_deltas = _snapshot_followers(notion, twitter, threads, log, dry_run=dry_run)

    rows = notion.get_performance_rows(since_days=ANALYSIS_WINDOW_DAYS)
    log.info("Loaded %d performance rows.", len(rows))

    x_writes = _x_writes_this_month(rows)
    budget = settings.X_MONTHLY_WRITE_BUDGET
    pct = 100 * x_writes / budget if budget else 0
    log.info("X write budget: ≥%d/%d used this calendar month (%.0f%%) — "
             "threads/CTA replies add extra; the developer portal is ground truth.",
             x_writes, budget, pct)
    if budget and pct >= 80:
        log.warning("X write budget at %.0f%% — expect 402s soon; consider fewer X slots or a tier upgrade.", pct)

    refreshed = _refresh_metrics(rows, notion, twitter, threads, log, dry_run=dry_run)
    log.info("Refreshed metrics for %d posts.", refreshed)

    points = [_to_point(r) for r in rows]
    points = [p for p in points if p.engagement_rate is not None]
    log.info("Usable data points (with impressions): %d", len(points))

    x_points = [p for p in points if p.platform == "X"]
    th_points = [p for p in points if p.platform == "Threads"]

    slot_rank = ranked(points, lambda p: p.slot)
    type_rank = ranked(points, lambda p: p.content_type)
    _log_ranking(log, "Slot", slot_rank)
    _log_ranking(log, "Content Type", type_rank)
    # Objective differs by platform: X is in follower-growth mode (growth proxy),
    # Threads optimizes engagement (funnel).
    _log_ranking(log, "Hook · X (growth)", ranked(x_points, lambda p: p.hook, metric=_growth))
    _log_ranking(log, "Hook · X (engagement)", ranked(x_points, lambda p: p.hook))
    _log_ranking(log, "Hook · Threads (engagement)", ranked(th_points, lambda p: p.hook))
    # Per-platform tag rankings — only when the tag has ≥2 distinct values.
    for plat, pts in (("X", x_points), ("Threads", th_points)):
        for tag in REPORT_TAGS:
            r = ranked_by_tag(pts, tag)
            if len({k for k, _, _ in r}) >= 2:
                _log_ranking(log, f"{tag} · {plat}", r)
    # X link A/B (W5): engagement per arm.
    link_ab = ranked_by_tag(x_points, "x_link_arm")
    _log_ranking(log, "X link A/B (engagement)", link_ab)

    best_hook_by_platform = {
        "X": best_hook(x_points, min_n=MIN_CELL_N, metric=_growth),
        "Threads": best_hook(th_points, min_n=MIN_CELL_N),
    }
    best_hook_by_platform = {k: v for k, v in best_hook_by_platform.items() if v}

    summary = {
        "rows": len(rows),
        "x_writes_month": x_writes,
        "data_points": len(points),
        "follower_deltas": follower_deltas,
        "best_slots": best_slots(points, top=2, min_n=MIN_CELL_N),
        "best_content_types": best_content_types(points, min_n=MIN_CELL_N),
        "best_hook": best_hook(points, min_n=MIN_CELL_N),
        "best_hook_by_platform": best_hook_by_platform,
        "link_ab": link_ab,
        "rules_updated": False,
    }

    if len(points) < MIN_DATA_POINTS:
        log.info("Only %d/%d data points — not updating Agent Rules yet.", len(points), MIN_DATA_POINTS)
        return summary

    notes = _build_notes(slot_rank, type_rank, best_hook_by_platform, link_ab, follower_deltas)
    confidence = min(100, round(100 * len(points) / FULL_CONFIDENCE_POINTS))
    evidence_ids = [
        r["post_id"] for r in rows
        if r.get("post_id") and not r["post_id"].startswith("DRYRUN-")
    ]
    summary["confidence"] = confidence

    if dry_run:
        log.info("[dry-run] would update Agent Rules (confidence=%d): %s", confidence, summary)
        return summary

    loop_iteration = notion.get_next_loop_iteration()
    summary["rules_updated"] = notion.write_rules(
        daily_limit=settings.DAILY_HARD_LIMIT,
        best_hook=summary["best_hook"],
        best_slots=summary["best_slots"],
        best_content_types=summary["best_content_types"],
        best_hook_by_platform=best_hook_by_platform,
        confidence=confidence,
        evidence_post_ids=evidence_ids,
        loop_iteration=loop_iteration,
        summary=notes,
    )
    log.info(
        "Agent Rules %s (loop iteration %d, confidence %d) | hooks X=%s Threads=%s.",
        "updated" if summary["rules_updated"] else "not written (DB unset)",
        loop_iteration, confidence,
        best_hook_by_platform.get("X", "—"), best_hook_by_platform.get("Threads", "—"),
    )
    return summary


def _x_writes_this_month(rows) -> int:
    """Lower-bound estimate of X write credits used this calendar month: one
    per X Performance row (with root-only threads and no CTA reply, one row =
    one write; historical thread/CTA rows under-count, hence 'at least')."""
    month_start = hkt_now_month_start()
    count = 0
    for r in rows:
        pid = r.get("post_id") or ""
        if pid.startswith("DRYRUN-") or not r.get("posted_at"):
            continue
        if (r.get("platform") or "X") != "X":
            continue
        posted = parse_notion_datetime(r["posted_at"], settings.TZ_NAME)
        if posted >= month_start:
            count += 1
    return count


def hkt_now_month_start():
    from core.timeutil import now as hkt_now
    ref = hkt_now(settings.TZ_NAME)
    return ref.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _refresh_metrics(rows, notion, twitter, threads, log, *, dry_run: bool) -> int:
    """Pull fresh engagement for real (non dry-run) posts in the refresh window
    and write the numbers back to Notion. Rows are routed to the platform that
    published them — X ids to the X API, Threads ids to the Threads insights
    API. Mutates `rows` in place."""
    now = datetime.now(timezone.utc)
    x_rows: dict[str, dict] = {}
    threads_rows: dict[str, dict] = {}
    for r in rows:
        pid = r.get("post_id") or ""
        if not pid or pid.startswith("DRYRUN-") or not r.get("posted_at"):
            continue
        posted = parse_notion_datetime(r["posted_at"], settings.TZ_NAME).astimezone(timezone.utc)
        age_hours = (now - posted).total_seconds() / 3600
        if not (REFRESH_MIN_AGE_HOURS <= age_hours < REFRESH_MAX_AGE_HOURS):
            continue  # one read per post, on its second night — never again
        if (r.get("platform") or "X") == "Threads":
            threads_rows[pid] = r
        else:
            x_rows[pid] = r

    if dry_run or not (x_rows or threads_rows):
        return 0

    metrics: dict[str, dict] = {}
    if x_rows:
        try:
            metrics.update(twitter.get_metrics(list(x_rows)))
        except Exception as exc:
            log.warning("X metrics refresh failed: %s", exc)
    if threads_rows:
        if threads is None:
            log.info("Skipping %d Threads rows — THREADS_ACCESS_TOKEN not set.", len(threads_rows))
        else:
            try:
                metrics.update(threads.get_insights(list(threads_rows)))
            except Exception as exc:
                log.warning("Threads insights refresh failed: %s", exc)

    by_id = {**x_rows, **threads_rows}
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
        # Growth-proxy signals have no number column — merge them into the row's
        # machine tags (both persisted and in-memory so this run's analysis sees
        # them). Only keys the API actually returned.
        extra = {k: m[k] for k in ("bookmarks", "quotes", "profile_clicks") if k in m}
        row.setdefault("tags", {}).update(extra)
        notion.update_performance_metrics(
            row["page_id"],
            {
                Performance.IMPRESSIONS: row["impressions"],
                Performance.LIKES: row["likes"],
                Performance.REPLIES: row["replies"],
                Performance.REPOSTS: row["reposts"],
                Performance.LINK_CLICKS: row["link_clicks"],
            },
            tags_merge=extra or None,
        )
        updated += 1
    return updated


def _to_point(row: dict) -> DataPoint:
    slot = None
    if row.get("posted_at"):
        dt = parse_notion_datetime(row["posted_at"], settings.TZ_NAME)
        slot = nearest_slot(dt, settings.POST_SLOTS_HKT)
    tags = row.get("tags") or {}
    # hook: prefer the machine tag, fall back to the Hook Used select label.
    hook = tags.get("hook") or ((row.get("hook_used") or "")[:1] or None)
    return DataPoint(
        slot=slot,
        content_type=row.get("content_type"),
        hook=hook,
        platform=row.get("platform") or tags.get("platform") or "X",
        composition=f"v{int(row.get('loop_version') or 1)}",
        impressions=row.get("impressions", 0.0),
        likes=row.get("likes", 0.0),
        replies=row.get("replies", 0.0),
        reposts=row.get("reposts", 0.0),
        link_clicks=row.get("link_clicks", 0.0),
        bookmarks=float(tags.get("bookmarks", 0.0) or 0.0),
        quotes=float(tags.get("quotes", 0.0) or 0.0),
        profile_clicks=float(tags.get("profile_clicks", 0.0) or 0.0),
        tags=tags,
    )


def _log_ranking(log, label, rows) -> None:
    if not rows:
        log.info("%s ranking: (no data)", label)
        return
    pretty = ", ".join(f"{k}={rate:.2%}(n={n})" for k, rate, n in rows)
    log.info("%s ranking: %s", label, pretty)


def _snapshot_followers(notion, twitter, threads, log, *, dry_run: bool) -> dict:
    """Record today's follower count for each platform and return the 7-day
    delta per platform. Best-effort: any failure logs and skips that platform."""
    today = hkt_now(settings.TZ_NAME).date().isoformat()
    deltas: dict[str, Optional[int]] = {}
    getters = {"X": getattr(twitter, "get_follower_count", None),
               "Threads": getattr(threads, "get_follower_count", None) if threads else None}
    for platform, getter in getters.items():
        if getter is None:
            continue
        try:
            count = getter()
        except Exception as exc:  # never fail the run on telemetry
            log.warning("%s follower snapshot failed: %s", platform, exc)
            count = None
        if count is None:
            continue
        try:
            history = notion.read_follower_history(platform)
        except Exception as exc:
            log.warning("%s follower history unreadable: %s", platform, exc)
            history = {}
        deltas[platform] = _follower_delta(history, count, days=7)
        history[today] = int(count)
        if not dry_run:
            try:
                notion.write_follower_history(platform, history)
            except Exception as exc:
                log.warning("%s follower history not written: %s", platform, exc)
        log.info("%s followers: %d (7d %s)", platform, count, _signed(deltas[platform]))
    return deltas


def _follower_delta(history: dict, current: int, days: int = 7) -> Optional[int]:
    """current − the count from ~`days` ago (the oldest snapshot within the
    window; None if there is no baseline yet)."""
    if not history:
        return None
    cutoff = (hkt_now(settings.TZ_NAME).date()).toordinal() - days
    older = {d: c for d, c in history.items() if _ordinal(d) is not None and _ordinal(d) <= cutoff}
    baseline = older[max(older)] if older else history[min(history)]
    try:
        return int(current) - int(baseline)
    except (TypeError, ValueError):
        return None


def _ordinal(iso_date: str):
    try:
        return datetime.strptime(iso_date, "%Y-%m-%d").date().toordinal()
    except (TypeError, ValueError):
        return None


def _signed(v) -> str:
    return "n/a" if v is None else f"{v:+d}"


def _build_notes(slot_rank, type_rank, best_hook_by_platform, link_ab, follower_deltas) -> str:
    def fmt(rows):
        return "; ".join(f"{k}: {rate:.2%} (n={n})" for k, rate, n in rows) or "n/a"
    hooks = ", ".join(f"{k}={v}" for k, v in best_hook_by_platform.items()) or "n/a"
    followers = ", ".join(f"{k} {_signed(v)}" for k, v in follower_deltas.items()) or "n/a"
    return (
        f"Slots → {fmt(slot_rank)}\n"
        f"Content Types → {fmt(type_rank)}\n"
        f"Best Hook by platform → {hooks}\n"
        f"X link A/B (engagement) → {fmt(link_ab)}\n"
        f"Followers (7d) → {followers}"
    )
