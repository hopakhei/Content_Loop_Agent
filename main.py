"""LOOP entry point.

    python main.py --loop 1                  # POST (uses current cron slot)
    python main.py --loop 1 --dry-run        # simulate, never touches X/Notion writes
    python main.py --loop 1 --slot 12:30 --yes
    python main.py --loop 2 [--dry-run]      # LEARN
    python main.py --loop 3 --issue 102 --article-file article.txt [--dry-run]
    python main.py --loop 3 --all            # fission every articles/<issue>.(md|txt)
    python main.py --check                   # read-only Notion + X preflight (no posting)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from config import settings
from utils.logging_setup import setup_logging

LOOP_NAMES = {1: "post", 2: "learn", 3: "generate"}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="loop", description="LOOP — 90s.pm.investing content pipeline")
    p.add_argument("--loop", type=int, choices=[1, 2, 3], help="Which loop to run")
    p.add_argument("--check", action="store_true",
                   help="Read-only preflight: verify Notion DB access + X credentials, then exit")
    p.add_argument("--inspect-threads", action="store_true",
                   help="Read-only: show how recently-posted Threads drafts composed (segments + CTA), then exit")
    p.add_argument("--inspect-days", type=int, default=3,
                   help="With --inspect-threads: look back this many days (default 3)")
    p.add_argument("--dry-run", action="store_true", default=settings.DRY_RUN,
                   help="Simulate the full flow without posting or writing to Notion")
    p.add_argument("--slot", help="Loop 1: override the posting slot (HH:MM)")
    p.add_argument("--yes", action="store_true", help="Loop 1: skip the pre-post countdown (headless cron)")
    p.add_argument("--issue", help="Loop 3: article Issue #")
    p.add_argument("--article-file", help="Loop 3: path to the article's full text")
    p.add_argument("--all", action="store_true", help="Loop 3: fission every articles/<issue>.(md|txt)")
    p.add_argument("--articles-dir", default="articles", help="Loop 3: directory of article texts (with --all)")
    p.add_argument("--fresh", action="store_true",
                   help="Loop 3: park each article's existing unposted drafts (Optimizing) before generating")
    p.add_argument("--cta-url", help="Loop 3: CTA URL (defaults to the Article's CTA URL)")
    p.add_argument("--article-id", help="Loop 3: Notion page id of the Article to relate drafts to")
    return p


def _run_check(logger) -> int:
    """Read-only preflight of Notion + X. Returns 0 if everything is reachable."""
    from services.notion import NotionService
    from services.twitter import TwitterService

    ok = True
    logger.info("Preflight — Notion databases:")
    for label, good, detail in NotionService(logger).verify_databases():
        logger.info("  %-18s %s — %s", label, "OK  " if good else "FAIL", detail)
        ok = ok and good

    logger.info("Preflight — X credentials:")
    try:
        handle = TwitterService(dry_run=False, logger=logger).verify()
        logger.info("  X auth             OK   — authenticated as @%s", handle)
    except Exception as exc:
        logger.error("  X auth             FAIL — %s", exc)
        ok = False

    logger.info("Preflight — Threads credentials:")
    if settings.THREADS_ACCESS_TOKEN:
        from services.threads import ThreadsService
        try:
            handle = ThreadsService(dry_run=False, logger=logger).verify()
            logger.info("  Threads auth       OK   — authenticated as @%s", handle)
        except Exception as exc:
            logger.error("  Threads auth       FAIL — %s", exc)
            ok = False
    else:
        logger.info("  Threads auth       SKIP — THREADS_ACCESS_TOKEN not set (optional)")

    logger.info("Preflight %s", "PASSED ✓" if ok else "FAILED ✗")
    return 0 if ok else 1


def _run_inspect_threads(logger, days: int) -> int:
    """Read-only: for each Threads post recorded in the last `days`, reproduce
    the composition from the (unchanged) draft so we can see exactly how many
    posts it became and whether the CTA is carried — the diagnostic for a
    truncated/hook-only Threads post."""
    from services.notion import NotionService
    from core.composition import (
        CTA_MARKER, CTA_PLACEHOLDERS, compose_posts, effective_cta_url,
    )

    notion = NotionService(logger)
    rows = notion.get_performance_rows(since_days=days)
    threads_rows = [r for r in rows if (r.get("platform") or "") == "Threads"]
    logger.info("Threads posts recorded in the last %dd: %d", days, len(threads_rows))

    for r in threads_rows:
        draft_id = r.get("draft_id")
        if not draft_id:
            continue
        draft = notion._build_draft(notion.client.pages.retrieve(page_id=draft_id))
        article = notion.get_article(draft.article_id) if draft.article_id else None
        cta = effective_cta_url(draft, article.cta_url if article else None)
        body = draft.post_body or ""
        # Compose WITHOUT a hook so the raw body split is visible.
        posts = compose_posts(draft, hook_text=None, cta_url=cta)
        cta_in_output = any((CTA_MARKER in p) or (cta and cta in p) for p in posts)
        logger.info("─" * 64)
        logger.info("post_id=%s | %s | type=%s | platforms=%s",
                    r.get("post_id"), draft.title, draft.content_type, draft.platforms)
        logger.info("cta_url=%s", cta or "(none)")
        logger.info("body: has_placeholder=%s has_👉=%s len=%d",
                    any(ph in body for ph in CTA_PLACEHOLDERS), CTA_MARKER in body, len(body))
        logger.info("→ composes into %d post(s); CTA present in output=%s", len(posts), cta_in_output)
        for i, p in enumerate(posts, 1):
            logger.info("   [%d/%d] %d chars | %s", i, len(posts), len(p),
                        p[:56].replace("\n", " ⏎ "))
    logger.info("Inspect done.")
    return 0


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.check:
        logger, log_path = setup_logging("check", dry_run=False)
        logger.info("=== Preflight check start | log=%s ===", log_path)
        try:
            return _run_check(logger)
        except Exception:
            logger.exception("Preflight failed with an unhandled error.")
            return 1

    if args.inspect_threads:
        logger, log_path = setup_logging("inspect", dry_run=False)
        logger.info("=== Inspect Threads composition | log=%s ===", log_path)
        try:
            return _run_inspect_threads(logger, args.inspect_days)
        except Exception:
            logger.exception("Inspect failed with an unhandled error.")
            return 1

    if not args.loop:
        build_parser().error("provide --loop {1,2,3} or --check")

    dry_run = bool(args.dry_run)
    loop_name = LOOP_NAMES[args.loop]
    logger, log_path = setup_logging(loop_name, dry_run)
    logger.info("=== LOOP %d (%s) start | dry_run=%s | log=%s ===", args.loop, loop_name, dry_run, log_path)

    try:
        if args.loop == 1:
            from loops import post_loop
            post_loop.run(dry_run=dry_run, slot=args.slot, assume_yes=args.yes, logger=logger)
        elif args.loop == 2:
            from loops import learn_loop
            learn_loop.run(dry_run=dry_run, logger=logger)
        else:
            from loops import generate_loop
            if args.all:
                generate_loop.run_batch(
                    articles_dir=args.articles_dir, dry_run=dry_run, fresh=args.fresh, logger=logger
                )
            elif args.issue and args.article_file:
                text = Path(args.article_file).read_text(encoding="utf-8")
                generate_loop.run(
                    issue_number=args.issue,
                    article_text=text,
                    cta_url=args.cta_url,
                    article_id=args.article_id,
                    dry_run=dry_run,
                    fresh=args.fresh,
                    logger=logger,
                )
            else:
                build_parser().error("Loop 3 requires --all, or --issue with --article-file")
    except KeyboardInterrupt:
        logger.warning("Interrupted by user.")
        return 130
    except Exception:
        logger.exception("Loop %d failed with an unhandled error.", args.loop)
        return 1

    logger.info("=== LOOP %d (%s) done ===", args.loop, loop_name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
