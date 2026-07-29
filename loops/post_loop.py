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
import random
import re
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
from core.tagging import COMPOSITION_VERSION, build_tags
from core.timeutil import nearest_slot, now as hkt_now
from services.errors import PartialThreadError
from services.notion import NotionService
from services.threads import ThreadsService
from services.twitter import TwitterService


def assign_arm(draft: Draft, platform: str, day: Optional[str] = None):
    """Arm for the live experiment, or None.

    Deterministic in (experiment, draft, day), so the two call sites — choosing
    the hook and stamping the tag — cannot disagree about which arm a post is in.
    Both pass the run's own date rather than letting it default, so a run that
    straddles midnight UTC still agrees with itself.

    Never raises. A malformed hypothesis card is a research problem; it must not
    stop the account from posting.
    """
    try:
        from research import experiments          # local: research/ is optional at runtime
        return experiments.assign(draft, platform, day=day)
    except Exception as exc:                      # noqa: BLE001 — posting outranks research
        logging.getLogger("loop.post").warning("experiment assignment skipped: %s", exc)
        return None


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
    if settings.POST_FRAMEWORKS_ONLY:
        # Strategy pivot: X/Threads promote the consulting-framework series, not
        # the numbered personal essays (101–201, 127…). Essay drafts have a
        # numeric issue in their title ("#127-01 …"); framework drafts use a
        # slug ("#porter-01 …"). Skip the numeric ones. Flip the flag to resume.
        _essay_title = re.compile(r"^#?\d+-")
        _base_eligible = eligible

        def eligible(d, _base=_base_eligible):  # noqa: F811 — intentional wrap
            return _base(d) and not _essay_title.match(d.title or "")
        log.info("POST_FRAMEWORKS_ONLY on — numbered essay drafts are paused on X/Threads.")
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
    run_day = ref.date().isoformat()
    hook_for = _pick_hooks_per_platform(draft, rules, targets, run_day)
    posts_for: dict = {}
    cta_for: dict = {}
    x_link_arm = _x_link_arm()  # W5: randomized link/no-link A/B on X
    for platform in targets:
        # X may carry a different destination than the article CTA (e.g. the
        # GitHub repo for build-in-public pieces — X suppresses Substack links
        # hardest). Threads always keeps the article's own CTA.
        plat_cta = _x_cta_for(draft, cta_url) if platform == "X" else cta_url
        if platform == "X" and plat_cta != cta_url:
            log.info("X CTA override: %s", plat_cta)
        base = compose_posts(draft, hook_for[platform][1], plat_cta)
        if platform == "X":
            # Link-free when the flag is off, or when the A/B assigns this post
            # to the no-link arm.
            if (not settings.X_INCLUDE_CTA) or x_link_arm == "no_link":
                base = strip_cta(base, plat_cta)
            if settings.X_LONGPOST:
                # Fold the whole argument into ONE X post (Premium ≤25k chars):
                # one write from the quota, the full framework in one read.
                joined = "\n\n".join(p for p in base if p and p.strip())
                base = [joined] if joined.strip() else []
            else:
                cap = max(1, settings.X_MAX_THREAD_POSTS)
                if len(base) > cap:
                    log.info("X variant: chain capped at %d of %d posts (write quota).", cap, len(base))
                    base = base[:cap]
        posts_for[platform] = base
        cta_for[platform] = plat_cta
        limit = (
            settings.X_LONGPOST_LIMIT
            if platform == "X" and settings.X_LONGPOST
            else 500 if platform == "Threads"
            else 280
        )
        for warning in length_warnings(base, limit=limit):
            log.warning("Length (%s): %s", platform, warning)
    if "X" in targets and settings.X_INCLUDE_CTA and settings.X_LINK_AB:
        log.info("X link A/B: this post is in the '%s' arm.", x_link_arm)

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
            plat_posts = posts_for[platform]
            plat_cta = cta_for[platform]
            cta_present = bool(plat_cta) and any(plat_cta in p for p in plat_posts)
            extra = {"x_link_arm": x_link_arm} if platform == "X" else {}
            arm = assign_arm(draft, platform, run_day)
            if arm:
                extra.update(arm.tag)
            extra = extra or None
            tags = build_tags(
                platform=platform, hook=hook_for[platform][0], posts=plat_posts,
                cta_url=plat_cta, cta_present=cta_present, title=draft.title, extra=extra,
            )
            notion.create_performance_record(
                draft_id=draft.id,
                post_id=ids[0],
                platform=platform,
                posted_at=ref,
                hook_label=hook_label,
                loop_version=COMPOSITION_VERSION,
                tags=tags,
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


_ISSUE_RE = re.compile(r"^#(\d+)-")


def _x_link_arm() -> str:
    """W5 randomized X link A/B — returns 'link' or 'no_link' for this post.
    Off (all 'no_link') when X_INCLUDE_CTA is false; all 'link' when the A/B
    itself is disabled; a fair coin otherwise. The tag always reflects the
    actual composition."""
    if not settings.X_INCLUDE_CTA:
        return "no_link"
    if not settings.X_LINK_AB:
        return "link"
    return "no_link" if random.random() < 0.5 else "link"


def _x_cta_for(draft: Draft, default_cta: Optional[str]) -> Optional[str]:
    """The CTA to use on X: the per-issue override (X_CTA_BY_ISSUE, keyed by
    the issue number in the draft title '#201-04 …') or the article CTA."""
    m = _ISSUE_RE.match(draft.title or "")
    if m:
        return settings.X_CTA_BY_ISSUE.get(m.group(1)) or default_cta
    return default_cta


def _pick_hooks_per_platform(draft: Draft, rules, targets: list, day: str) -> dict:
    """{platform: (hook_key, hook_text)}. Each platform is biased toward ITS OWN
    learned winner (Best Hook (X) / Best Hook (Threads), falling back to the
    pooled winner, else random). To keep cross-platform exploration, if a
    dual-platform draft independently picks the SAME variant for both, Threads
    is shifted to the next variant in cyclic order."""
    by_plat = getattr(rules, "best_hook_by_platform", {}) or {}
    picks = {p: select_hook(draft, rules, winner_override=by_plat.get(p)) for p in targets}
    available = draft.available_hooks()

    # A live experiment overrides the learned pick on its platform. It has to:
    # `select_hook` biases toward the current winner, and a randomised arm that
    # is then filtered through a preference for one of its own arms is not
    # randomised. Assignments that cannot be honoured return None and leave the
    # learned pick alone.
    for p in targets:
        a = assign_arm(draft, p, day)
        if a and a.hook_key and available.get(a.hook_key):
            picks[p] = (a.hook_key, available[a.hook_key])
    if ("X" in picks and "Threads" in picks and len(available) >= 2
            and picks["X"][0] and picks["X"][0] == picks["Threads"][0]):
        keys = sorted(available)
        alt = keys[(keys.index(picks["Threads"][0]) + 1) % len(keys)]
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
