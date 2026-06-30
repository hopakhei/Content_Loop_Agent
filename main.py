"""LOOP entry point.

    python main.py --loop 1                  # POST (uses current cron slot)
    python main.py --loop 1 --dry-run        # simulate, never touches X/Notion writes
    python main.py --loop 1 --slot 12:30 --yes
    python main.py --loop 2 [--dry-run]      # LEARN
    python main.py --loop 3 --issue 102 --article-file article.txt [--dry-run]
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
    p.add_argument("--dry-run", action="store_true", default=settings.DRY_RUN,
                   help="Simulate the full flow without posting or writing to Notion")
    p.add_argument("--slot", help="Loop 1: override the posting slot (HH:MM)")
    p.add_argument("--yes", action="store_true", help="Loop 1: skip the pre-post countdown (headless cron)")
    p.add_argument("--issue", help="Loop 3: article Issue #")
    p.add_argument("--article-file", help="Loop 3: path to the article's full text")
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

    logger.info("Preflight %s", "PASSED ✓" if ok else "FAILED ✗")
    return 0 if ok else 1


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
            if not args.issue or not args.article_file:
                build_parser().error("Loop 3 requires --issue and --article-file")
            text = Path(args.article_file).read_text(encoding="utf-8")
            from loops import generate_loop
            generate_loop.run(
                issue_number=args.issue,
                article_text=text,
                cta_url=args.cta_url,
                article_id=args.article_id,
                dry_run=dry_run,
                logger=logger,
            )
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
