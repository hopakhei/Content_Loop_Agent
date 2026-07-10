"""Loop 1 — POST.

讀草稿 → 發佈 → 標記已發.

Runs once per cron slot. Reads the daily quota from the Agent Rules (falling back
to DAILY_HARD_LIMIT), selects up to MAX_POSTS_PER_RUN drafts by the priority
ladder, publishes each to every platform it targets (X always; Threads when
THREADS_ACCESS_TOKEN is configured), and records the result in Notion — one
Post Performance row per platform, but one posting event toward the daily limit.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta
from typing import Optional

from config import settings
from config.schema import HOOK_FIELDS
from core.composition import (
    compose_posts,
    effective_cta_url,
    length_warnings,
    select_hook,
    strip_cta,
)
from core.models import Draft
from core.selection import make_eligibility, select_draft
from core.timeutil import nearest_slot, now as hkt_now
from services.errors import PartialThreadError
from services.notion import NotionService
from services.threads import ThreadsService
from services.twitter import TwitterService

# Stamped on every Post Performance row so Loop 2 can compare eras.
#   1 = CTA inline in the X post
#   2 = X post link-free, CTA in a self-reply
#   3 = X post link-free, no CTA (funnel de-prioritised while followers are low)
COMPOSITION_VERSION = 3


def run(
    dry_run: bool = False,
    slot: Optional[str] = None,
    assume_yes: bool = False,
    logger: Optional[logging.Logger] = None,
    notion: Optional[NotionService] = None,
    twitter: Optional[TwitterService] = None,
    threads: Optional[ThreadsService] = None,
) -> dict:
    """Execute one Loop-1 run. Returns a summary dict (also useful for tests)."""
    log = logger or logging.getLogger("loop.post")
    notion = notion or NotionService(log)

    publishers: dict = {}
    publishers["X"] = twitter or TwitterService(dry_run=dry_run, logger=log)
    if threads is not None:
        publishers["Threads"] = threads
    elif settings.THREADS_ACCESS_TOKEN:
        publishers["Threads"] = ThreadsService(dry_run=dry_run, logger=log)

    ref = hkt_now(settings.TZ_NAME)

    # X quota park: after a 402 (monthly write cap) Loop 1 records a rule and
    # posts without X until the recorded date passes (or the rule is deprecated
    # by hand in Notion).
    try:
        parked_until = notion.get_x_parked_until()
    except Exception as exc:  # never let the park check block posting
        log.warning("Could not read the X park rule (%s) — assuming X available.", exc)
        parked_until = None
    if parked_until:
        if ref.date() <= parked_until:
            log.warning("X parked until %s (monthly write quota) — posting without X.", parked_until)
            publishers.pop("X", None)
        else:
            log.info("X park (until %s) has expired — resuming X posting.", parked_until)
            if not dry_run:
                try:
                    notion.unpark_x()
                except Exception as exc:
                    log.warning("Could not deprecate the X park rule: %s", exc)

    eligible = make_eligibility(set(publishers))
    slot = slot or nearest_slot(ref, settings.POST_SLOTS_HKT)

    rules = notion.get_rules()
    daily_limit = rules.daily_limit if (rules and rules.daily_limit) else settings.DAILY_HARD_LIMIT

    total_today, per_article = notion.count_posts_today(ref)
    log.info(
        "Loop 1 POST | %s HKT | slot=%s | dry_run=%s | platforms=%s | posts today=%d/%d",
        ref.strftime("%Y-%m-%d %H:%M"), slot, dry_run, "+".join(sorted(publishers)), total_today, daily_limit,
    )

    # `failures` closes the loop: main.py exits non-zero when it's non-empty,
    # which fails the GitHub Actions job and fires the failure notice.
    summary = {"slot": slot, "dry_run": dry_run, "posted": [], "skipped": None, "failures": []}

    articles_by_id = {a.id: a for a in notion.list_articles()}

    for _ in range(max(1, settings.MAX_POSTS_PER_RUN)):
        if total_today >= daily_limit:
            summary["skipped"] = "daily-limit-reached"
            log.info("SKIP: daily limit reached (%d/%d).", total_today, daily_limit)
            break

        scheduled = notion.query_drafts_by_status("Scheduled")
        drafts = notion.query_drafts_by_status("Draft")

        chosen, reason = select_draft(
            slot, ref, scheduled, drafts, per_article, articles_by_id,
            tzname=settings.TZ_NAME, eligible=eligible,
        )
        if not chosen:
            summary["skipped"] = reason
            log.info("SKIP: no eligible draft (%s).", reason)
            break

        result = _publish_one(
            chosen, reason, rules, articles_by_id, notion, publishers, log,
            ref=ref, dry_run=dry_run, assume_yes=assume_yes,
            failures=summary["failures"],
        )
        if result is None:  # aborted by user during preview
            summary["skipped"] = "aborted"
            break

        summary["posted"].append(result)
        total_today += 1
        if chosen.article_id:
            per_article[chosen.article_id] = per_article.get(chosen.article_id, 0) + 1

    log.info("Loop 1 done | posted=%d | skipped=%s", len(summary["posted"]), summary["skipped"])
    return summary


def _publish_one(
    draft: Draft,
    reason: str,
    rules,
    articles_by_id: dict,
    notion: NotionService,
    publishers: dict,
    log: logging.Logger,
    *,
    ref: datetime,
    dry_run: bool,
    assume_yes: bool,
    failures: Optional[list] = None,
) -> Optional[dict]:
    failures = failures if failures is not None else []
    article = articles_by_id.get(draft.article_id) if draft.article_id else None
    if article is None and draft.article_id:
        article = notion.get_article(draft.article_id)

    cta_url = effective_cta_url(draft, article.cta_url if article else None)

    # Target every platform the draft names that we have a publisher for
    # (a draft with no platforms defaults to X).
    targets = [p for p in (draft.platforms or ["X"]) if p in publishers]
    if not targets:
        log.warning("SKIP draft %s: no configured publisher for %s.", draft.title, draft.platforms)
        return None

    # Per-platform personalisation. The platforms rank differently, so each
    # gets its own final form:
    #  - Hook: X keeps the rules-weighted pick; a dual-platform draft gives
    #    Threads the NEXT hook variant — a cross-platform A/B on every post.
    #  - X posts link-free while the follower count is low (X_INCLUDE_CTA
    #    restores it) and chains are capped at X_MAX_THREAD_POSTS (every
    #    chained tweet costs a monthly write credit). Threads keeps the CTA
    #    and the full chain, and gets its own 500-char limit.
    hook_for = _pick_hooks_per_platform(draft, rules, targets)
    posts_for: dict = {}
    for platform in targets:
        base = compose_posts(draft, hook_for[platform][1], cta_url)
        if platform == "X":
            if not settings.X_INCLUDE_CTA:
                base = strip_cta(base, cta_url)
            cap = max(1, settings.X_MAX_THREAD_POSTS)
            if len(base) > cap:
                log.info("X variant: chain capped at %d of %d posts (write quota).", cap, len(base))
                base = base[:cap]
        posts_for[platform] = base
        limit = 500 if platform == "Threads" else 280
        for warning in length_warnings(base, limit=limit):
            log.warning("Length (%s): %s", platform, warning)

    if not any(posts_for.values()):
        log.warning("SKIP draft %s: composed to empty content.", draft.title)
        return None

    _show_preview(log, draft, posts_for, hook_for, reason, cta_url)
    if not _confirm(log, dry_run=dry_run, assume_yes=assume_yes):
        log.warning("Aborted by user before posting '%s'.", draft.title)
        return None

    results: dict = {}
    for platform in targets:
        hook_key = hook_for[platform][0]
        hook_label = HOOK_FIELDS[hook_key][1] if hook_key else None
        try:
            ids = publishers[platform].post_thread(posts_for[platform])
        except PartialThreadError as exc:
            # The root post is live — record it so the next slot doesn't
            # re-post duplicate content; the tail can be added by hand.
            log.error(
                "PARTIAL on %s for '%s': %d/%d posts live before failure (%s) — recording the root post.",
                platform, draft.title, len(exc.ids), len(posts_for[platform]), exc.cause,
            )
            failures.append({"platform": platform, "draft": draft.title,
                             "error": f"partial thread ({len(exc.ids)} live): {exc.cause}"})
            _park_x_if_quota_exhausted(platform, exc.cause, notion, log, dry_run=dry_run)
            ids = exc.ids
        except Exception as exc:
            log.error("FAILED on %s for '%s': %s", platform, draft.title, exc)
            failures.append({"platform": platform, "draft": draft.title, "error": str(exc)})
            _park_x_if_quota_exhausted(platform, exc, notion, log, dry_run=dry_run)
            continue
        results[platform] = ids
        if not dry_run:
            notion.create_performance_record(
                draft_id=draft.id,
                post_id=ids[0],
                platform=platform,
                posted_at=ref,
                hook_label=hook_label,
                loop_version=COMPOSITION_VERSION,
            )

    if not results:
        log.error("SKIP draft %s: every target platform failed.", draft.title)
        return None
    if not dry_run:
        notion.mark_draft_posted(draft.id)

    for platform, ids in results.items():
        log.info(
            "POSTED ✓ '%s' | platform=%s | reason=%s | hook=%s | posts=%d | post_id=%s",
            draft.title, platform, reason, hook_for[platform][0] or "none", len(ids), ids[0],
        )
    first = next(iter(results.values()))
    primary = "X" if "X" in results else next(iter(results))
    return {
        "draft_id": draft.id,
        "title": draft.title,
        "platforms": list(results),
        "post_ids": {p: ids[0] for p, ids in results.items()},
        "post_id": first[0],
        "tweet_ids": results.get("X", first),
        "reason": reason,
        "hook": hook_for[primary][0],
        "hooks_used": {p: hook_for[p][0] for p in results},
        "num_tweets": len(first),
    }


def _pick_hooks_per_platform(draft: Draft, rules, targets: list) -> dict:
    """{platform: (hook_key, hook_text)}. X keeps the rules-weighted pick; on a
    dual-platform draft Threads takes the NEXT hook variant (cyclic order), so
    every dual post is also a cross-platform hook A/B experiment."""
    base = select_hook(draft, rules)
    picks = {p: base for p in targets}
    available = draft.available_hooks()
    if "X" in picks and "Threads" in picks and base[0] and len(available) >= 2:
        keys = sorted(available)
        alt = keys[(keys.index(base[0]) + 1) % len(keys)]
        picks["Threads"] = (alt, available[alt])
    return picks


def _park_x_if_quota_exhausted(platform, exc, notion, log, *, dry_run: bool) -> None:
    """On X's 402 (monthly write cap), park X until the 1st of next month so
    later runs post Threads-only instead of failing every slot. Resume earlier
    by deprecating/deleting the 'X Parked Until' rule in Agent Rules."""
    if platform != "X" or dry_run:
        return
    msg = str(exc)
    if not ("402" in msg or "Payment Required" in msg or "credits" in msg.lower()):
        return
    until = _first_of_next_month(hkt_now(settings.TZ_NAME).date())
    try:
        notion.park_x_until(until)
        log.error(
            "X monthly write quota exhausted — parked X until %s. "
            "(Deprecate the '%s' rule in Agent Rules to resume earlier, e.g. after a tier upgrade.)",
            until, "X Parked Until",
        )
    except Exception as e:
        log.warning("Could not write the X park rule: %s", e)


def _first_of_next_month(today: date) -> date:
    return (today.replace(day=1) + timedelta(days=32)).replace(day=1)


def _show_preview(log, draft, posts_for: dict, hook_for: dict, reason, cta_url) -> None:
    sep = "─" * 56
    log.info(sep)
    plat_desc = " + ".join(
        f"{p}(hook={hook_for[p][0] or 'none'}, {len(posts_for[p])} post{'s' if len(posts_for[p]) > 1 else ''})"
        for p in posts_for
    )
    log.info("PREVIEW | %s | type=%s | reason=%s | → %s",
             draft.title, draft.content_type or "?", reason, plat_desc)
    log.info("CTA: %s", cta_url or "(none)")
    primary = "X" if "X" in posts_for else next(iter(posts_for))
    for i, text in enumerate(posts_for[primary], start=1):
        tag = f"[{i}/{len(posts_for[primary])}]" if len(posts_for[primary]) > 1 else ""
        log.info("%s (%s, %d chars)", tag, primary, len(text))
        for line in text.splitlines() or [""]:
            log.info("  | %s", line)
    for p, posts in posts_for.items():
        if p != primary and posts:
            log.info("(%s opens with) | %s", p, posts[0].splitlines()[0] if posts[0] else "")
    log.info(sep)


def _confirm(log, *, dry_run: bool, assume_yes: bool) -> bool:
    """Spec's irreversibility guard: wait PREVIEW_COUNTDOWN_SECONDS so a human can
    Ctrl+C. Skipped on dry-run or when --yes is passed (e.g. headless cron)."""
    seconds = settings.PREVIEW_COUNTDOWN_SECONDS
    if dry_run or assume_yes or seconds <= 0:
        return True
    log.info("Posting in %ds… press Ctrl+C to abort.", seconds)
    try:
        time.sleep(seconds)
    except KeyboardInterrupt:
        return False
    return True
