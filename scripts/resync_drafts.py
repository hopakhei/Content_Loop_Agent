#!/usr/bin/env python3
"""Push edited unit files back into the Notion drafts they already created.

The insert path is deliberately one-way. `generate-pending.yml` inserts a unit
once, writes the slug into `state/inserted_units.txt`, and skips it forever
after — which is what makes the cron idempotent and what stops a draft being
created twice.

The cost of that design only shows up later: editing `units/<slug>.md` after
insertion changes nothing anybody reads. The file is right, git is right, CI is
green, and the post loop keeps publishing the old wording out of Notion. That is
the same silent-success shape the runway meter exists to kill, so it gets the
same treatment — a job that says out loud what it changed and what it could not.

    python scripts/resync_drafts.py --dry-run   # print the drift, write nothing
    python scripts/resync_drafts.py             # push edits into Notion

Only un-posted drafts (Draft / Scheduled) are touched. A posted draft is
history: the audience already read it, and the Performance rows are scored
against what shipped, so rewriting it would corrupt the experiment corpus that
`research/cards.py` reconstructs from git.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.schema import Drafts                       # noqa: E402
from core.parsing import parse_units                   # noqa: E402

UNITS = ROOT / "units"
LEDGER = ROOT / "state" / "inserted_units.txt"
POSTED = ROOT / "state" / "posted_units.txt"

POSTED_HEADER = """\
# Framework slugs whose Thread draft has already posted. Written by
# scripts/resync_drafts.py from Notion on every generate-pending run, so the
# offline checks can tell "still fixable" from "the audience already read it".
# Hand edits get overwritten; change Notion, not this file.
"""

# Draft titles are "#<slug>-<NN> <Content Type>" (loops/generate_loop.py). The
# slug match is greedy so the split lands on the LAST hyphen: slugs contain both
# hyphens and digits (mckinsey-7s, core-vs-non-core), and a lazy match cut
# `mckinsey-7s-23` at the wrong one and lost the draft entirely.
_TITLE = re.compile(r"^#(?P<slug>.+)-(?P<num>\d{2})\s")


def inserted_slugs() -> set[str]:
    if not LEDGER.exists():
        return set()
    return {ln.strip() for ln in LEDGER.read_text("utf-8").splitlines() if ln.strip()}


def unit_text(slug: str) -> tuple[dict, str]:
    """(hooks, post_body) as the parser sees them — the same values the insert
    path would have written, so a comparison here means what it looks like."""
    unit = parse_units((UNITS / f"{slug}.md").read_text("utf-8"))[0]
    return unit.hooks, unit.post_body


def drift(draft, hooks: dict, post_body: str) -> list[str]:
    """Which fields differ. Empty means the draft already matches the file."""
    out = []
    for key in ("A", "B", "C"):
        want = (hooks.get(key) or "").strip()
        if want and want != (draft.hooks.get(key) or "").strip():
            out.append(f"Hook {key}")
    if post_body.strip() != (draft.post_body or "").strip():
        out.append("Post Body")
    return out


def posted_slugs() -> set[str]:
    """Framework slugs already published, read off the committed ledger."""
    if not POSTED.exists():
        return set()
    return {ln.strip() for ln in POSTED.read_text("utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")}


def _write_posted(slugs: list[str], log: logging.Logger) -> None:
    """Rewrite the posted ledger, but never shrink it on a bad read.

    `no_live_draft` is derived from a Notion query. If that query returns
    partial results the list looks shorter, and a plain overwrite would mark
    published units as unpublished — which is how a check starts demanding
    edits to posts the audience read weeks ago.
    """
    merged = sorted(posted_slugs() | set(slugs))
    POSTED.write_text(POSTED_HEADER + "\n".join(merged) + "\n", encoding="utf-8")
    log.info("posted ledger: %d slugs", len(merged))


def run(dry_run: bool = False, log: logging.Logger | None = None) -> dict:
    from services.notion import NotionService

    log = log or logging.getLogger("resync")
    notion = NotionService(log)

    live = notion.query_drafts_by_status(Drafts.STATUS_DRAFT) + \
        notion.query_drafts_by_status(Drafts.STATUS_SCHEDULED)
    by_slug: dict[str, list] = {}
    for d in live:
        m = _TITLE.match(d.title or "")
        if m:
            by_slug.setdefault(m.group("slug"), []).append(d)

    updated, in_sync, no_live_draft, missing_file = [], [], [], []
    for slug in sorted(inserted_slugs()):
        if slug[:1].isdigit():
            continue                       # numbered essays: separate pipeline
        if not (UNITS / f"{slug}.md").exists():
            missing_file.append(slug)
            continue
        drafts = by_slug.get(slug)
        if not drafts:
            no_live_draft.append(slug)     # already posted, or parked
            continue
        hooks, body = unit_text(slug)
        for d in drafts:
            fields = drift(d, hooks, body)
            if not fields:
                in_sync.append(slug)
                continue
            log.info("%s %s: %s", "[dry-run] would update" if dry_run else "updating",
                     d.title, ", ".join(fields))
            if not dry_run:
                notion.update_draft_text(d.id, hooks, body)
            updated.append(slug)

    log.info("resync: %d updated, %d already in sync, %d with no un-posted draft.",
             len(updated), len(in_sync), len(no_live_draft))

    # Commit which slugs have gone out. The style and grounding checks run
    # offline with no Notion token, and without this they cannot tell content
    # that can still be fixed from content the audience already read — which is
    # the difference between an alarm worth having and one that can never be
    # silenced. This job already holds the answer; writing it down is free.
    if not dry_run:
        _write_posted(sorted(no_live_draft), log)
    # A ledger entry whose file has vanished is a real inconsistency, not a
    # no-op: something can post from Notion that no longer exists in git, and
    # nothing else in the pipeline checks for it.
    if missing_file:
        log.warning("ledger names %d unit(s) with no file on disk: %s",
                    len(missing_file), ", ".join(missing_file))
    return {"updated": updated, "in_sync": in_sync,
            "no_live_draft": no_live_draft, "missing_file": missing_file}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true",
                    help="print what would change without writing to Notion")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
