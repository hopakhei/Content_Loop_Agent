"""Loop 1 — POST.

讀草稿 → 發佈 → 標記已發.

Runs once per cron slot. Reads the daily quota from Posting Rules (falling back
to DAILY_HARD_LIMIT), selects up to MAX_POSTS_PER_RUN drafts by the priority
ladder, publishes them to X, and records the result in Notion.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional

from config import settings
from config.schema import HOOK_FIELDS
from core.composition import compose_posts, effective_cta_url, length_warnings, select_hook
from core.models import Draft
from core.selection import select_draft
from core.timeutil import nearest_slot, now as hkt_now
from services.notion import NotionService
from services.twitter import TwitterService


def run(
    dry_run: bool = False,
    slot: Optional[str] = None,
    assume_yes: bool = False,
    logger: Optional[logging.Logger] = None,
    notion: Optional[NotionService] = None,
    twitter: Optional[TwitterService] = None,
) -> dict:
    """Execute one Loop-1 run. Returns a summary dict (also useful for tests)."""
    log = logger or logging.getLogger("loop.post")
    notion = notion or NotionService(log)
    twitter = twitter or TwitterService(dry_run=dry_run, logger=log)

    ref = hkt_now(settings.TZ_NAME)
    slot = slot or nearest_slot(ref, settings.POST_SLOTS_HKT)

    rules = notion.get_posting_rules()
    daily_limit = rules.daily_limit if (rules and rules.daily_limit) else settings.DAILY_HARD_LIMIT

    total_today, per_article = notion.count_posts_today(ref)
    log.info(
        "Loop 1 POST | %s HKT | slot=%s | dry_run=%s | posts today=%d/%d",
        ref.strftime("%Y-%m-%d %H:%M"), slot, dry_run, total_today, daily_limit,
    )

    summary = {"slot": slot, "dry_run": dry_run, "posted": [], "skipped": None}

    articles_by_id = {a.id: a for a in notion.list_articles()}

    for _ in range(max(1, settings.MAX_POSTS_PER_RUN)):
        if total_today >= daily_limit:
            summary["skipped"] = "daily-limit-reached"
            log.info("SKIP: daily limit reached (%d/%d).", total_today, daily_limit)
            break

        scheduled = notion.query_drafts_by_status("Scheduled")
        drafts = notion.query_drafts_by_status("Draft")

        chosen, reason = select_draft(
            slot, ref, scheduled, drafts, per_article, articles_by_id, tzname=settings.TZ_NAME
        )
        if not chosen:
            summary["skipped"] = reason
            log.info("SKIP: no eligible draft (%s).", reason)
            break

        result = _publish_one(
            chosen, reason, rules, articles_by_id, notion, twitter, log,
            ref=ref, dry_run=dry_run, assume_yes=assume_yes,
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
    twitter: TwitterService,
    log: logging.Logger,
    *,
    ref: datetime,
    dry_run: bool,
    assume_yes: bool,
) -> Optional[dict]:
    article = articles_by_id.get(draft.article_id) if draft.article_id else None
    if article is None and draft.article_id:
        article = notion.get_article(draft.article_id)

    cta_url = effective_cta_url(draft, article.cta_url if article else None)
    hook_key, hook_text = select_hook(draft, rules)
    posts = compose_posts(draft, hook_text, cta_url)

    if not posts:
        log.warning("SKIP draft %s: composed to empty content.", draft.title)
        return None

    for warning in length_warnings(posts):
        log.warning("Length: %s", warning)

    _show_preview(log, draft, posts, reason, hook_key, cta_url)
    if not _confirm(log, dry_run=dry_run, assume_yes=assume_yes):
        log.warning("Aborted by user before posting '%s'.", draft.title)
        return None

    tweet_ids = twitter.post_thread(posts)
    post_id = tweet_ids[0]

    hook_label = HOOK_FIELDS[hook_key][1] if hook_key else None
    if not dry_run:
        notion.mark_draft_posted(draft.id)
        notion.create_performance_record(
            draft_id=draft.id,
            post_id=post_id,
            platform="X",
            posted_at=ref,
            hook_label=hook_label,
            loop_version=1,
        )

    log.info(
        "POSTED ✓ '%s' | reason=%s | hook=%s | tweets=%d | post_id=%s",
        draft.title, reason, hook_key or "none", len(tweet_ids), post_id,
    )
    return {
        "draft_id": draft.id,
        "title": draft.title,
        "post_id": post_id,
        "tweet_ids": tweet_ids,
        "reason": reason,
        "hook": hook_key,
        "num_tweets": len(tweet_ids),
    }


def _show_preview(log, draft, posts, reason, hook_key, cta_url) -> None:
    sep = "─" * 56
    log.info(sep)
    log.info("PREVIEW | %s | type=%s | reason=%s | hook=%s",
             draft.title, draft.content_type or "?", reason, hook_key or "none")
    log.info("CTA: %s", cta_url or "(none)")
    for i, text in enumerate(posts, start=1):
        tag = f"[{i}/{len(posts)}]" if len(posts) > 1 else ""
        log.info("%s (%d chars)", tag, len(text))
        for line in text.splitlines() or [""]:
            log.info("  | %s", line)
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
