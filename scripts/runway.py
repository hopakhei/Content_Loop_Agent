#!/usr/bin/env python3
"""How many days of content are left, and fail loudly before it reaches zero.

The failure this exists to prevent has now happened twice. Both times the
symptom was the same: a scheduled job ran, found nothing to publish, logged a
notice, and exited zero. Nothing was broken, so nothing complained — the
channel simply went quiet, and the first signal was a human noticing days
later that no post had gone out.

A green tick on a job that produced nothing is the disease. The cure is a
number with a floor under it: count what is actually queued, divide by the
publishing rate, and fail the job while there is still a week to react.

    python scripts/runway.py            # print the report
    python scripts/runway.py --check    # exit 1 when any channel is short

`--check` is what the cron runs. It fails every day the runway is short, which
is intended: the nag stops the moment somebody writes the next batch, and
`frameworks/next.md` already says which frameworks those should be.
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# `python scripts/runway.py` puts scripts/ on sys.path, not the repo root, so
# the Notion branch below dies with ModuleNotFoundError — and only on a machine
# that has a token, which is CI and not a laptop. The first run of this file in
# CI failed exactly there.
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

QUEUE = ROOT / "queue" / "carousel_queue.txt"
UNITS = ROOT / "units"
LEDGER = ROOT / "state" / "inserted_units.txt"
INDEX = ROOT / "frameworks" / "index.csv"
FACTSHEETS = ROOT / "frameworks" / "factsheets"

# Both channels publish once a day (carousel-drip at 12:30 HKT, post loop at
# the same slot), so a queued item is a day of runway.
PER_DAY = 1

# The floor, and the batch that has to clear it. These two numbers are a pair,
# and getting the pair wrong is how a monitor turns into wallpaper: an alarm
# that fires the day after every batch is one that gets muted, and a muted
# alarm is worse than none because it looks like coverage.
#
# A batch of BATCH_DAYS buys BATCH_DAYS - WARN_DAYS days of quiet before the
# nag resumes, so the batch has to be comfortably larger than the floor.
# Five days is still a full working week of notice against a one-a-day
# schedule, and twelve is the shortlist frameworks/next.md hands you.
WARN_DAYS = 5
BATCH_DAYS = 12

# The deep reserve has its own floor. 84 frameworks with prose on disk is about
# three months at one a day; the other 63 exist only as contents-page entries,
# because the Drive reader truncates each source PDF around page 80. When the
# writable pile drops to two batches, extracting the rest stops being a someday
# job — and two batches is months of warning, which is the point of saying it
# early rather than discovering it on the day the shortlist comes back empty.
RESERVE_FLOOR = 2 * BATCH_DAYS

# The reserve above is measured on `frameworks/raw/`, which is gitignored — it
# only exists on a machine that has processed the source PDFs. Any session
# cloned fresh from git, including the auto-producer Routine, sees none of it.
#
# That gap is why the Routine has fired repeatedly and committed nothing: it
# was asked to write frameworks whose source material lives somewhere it never
# runs. `frameworks/factsheets/` is the committed, own-words substitute, and
# this floor measures the only reserve a hands-off session can actually spend.
# One batch, because topping it up needs a session with the briefs — so the
# warning has to arrive while there is still a batch in hand.
FACTSHEET_FLOOR = BATCH_DAYS

# Numbered essays (101-201, 127) run on a separate pipeline and are filtered
# out of the framework feed by POST_FRAMEWORKS_ONLY — counting them as runway
# is exactly the mistake that made an empty queue look full.
ESSAY_TITLE = re.compile(r"^#?\d+-")


def _framework_slugs() -> set[str]:
    return {p.stem for p in UNITS.glob("*.md") if not p.stem.isdigit()}


def _inserted() -> set[str]:
    if not LEDGER.exists():
        return set()
    return {ln.strip() for ln in LEDGER.read_text("utf-8").splitlines() if ln.strip()}


def queue_depth() -> int:
    """Carousel specs waiting to drip."""
    if not QUEUE.exists():
        return 0
    return sum(1 for ln in QUEUE.read_text("utf-8").splitlines()
               if ln.strip() and not ln.lstrip().startswith("#"))


def pending_inserts() -> int:
    """Units written but not yet turned into Notion drafts. These become
    X/Threads runway at the next generate-pending run, so they count."""
    return len(_framework_slugs() - _inserted())


def notion_draft_count() -> int:
    """Un-posted framework drafts sitting in Notion.

    Raises if NOTION_TOKEN is set but the query fails. A token that has gone
    stale must not quietly turn this channel into 'unknown' — that would
    reintroduce the silent-success failure inside the check meant to catch it.
    """
    from services.notion import NotionService
    notion = NotionService()
    drafts = notion.query_drafts_by_status("Draft") + notion.query_drafts_by_status("Scheduled")
    return sum(1 for d in drafts if not ESSAY_TITLE.match(d.title or ""))


def reserve() -> dict:
    """Material for future batches, straight off the ledger."""
    counts = {"writable": 0, "needs_prose": 0}
    if not INDEX.exists():
        return counts
    for row in csv.DictReader(INDEX.open(encoding="utf-8")):
        if row["status"] != "backlog":
            continue
        counts["writable" if row["source"] == "brief" else "needs_prose"] += 1
    return counts


def factsheets_available() -> int:
    """Committed fact sheets for frameworks that have not shipped yet.

    A fact sheet whose framework is already written is spent, so it does not
    count — the number has to answer "how much can a fresh clone write from
    today", not "how many files are in the folder"."""
    if not FACTSHEETS.exists():
        return 0
    written = _framework_slugs()
    return sum(1 for p in FACTSHEETS.glob("*.md") if p.stem not in written)


def report() -> dict:
    """Days of runway per channel. `None` means the channel could not be read
    (no Notion token) — never treated as healthy, only as unmeasured."""
    ig = queue_depth()
    pending = pending_inserts()

    live_drafts = None
    if os.getenv("NOTION_TOKEN"):
        live_drafts = notion_draft_count()

    xt = None if live_drafts is None else live_drafts + pending
    return {
        "instagram_days": ig // PER_DAY,
        "x_threads_days": None if xt is None else xt // PER_DAY,
        "notion_drafts": live_drafts,
        "pending_inserts": pending,
        "reserve": reserve(),
        "factsheets": factsheets_available(),
    }


def _fact_txt(r: dict) -> str:
    n = r.get("factsheets")
    return "unmeasured" if n is None else f"{n} unwritten"


def render(r: dict) -> str:
    ig, xt = r["instagram_days"], r["x_threads_days"]
    res = r["reserve"]
    xt_txt = "unmeasured (no NOTION_TOKEN)" if xt is None else f"{xt} days"
    detail = "" if r["notion_drafts"] is None else (
        f" ({r['notion_drafts']} Notion drafts + {r['pending_inserts']} awaiting insert)")
    return "\n".join([
        "Content runway",
        f"  Instagram (carousel drip) : {ig} days",
        f"  X / Threads (post loop)   : {xt_txt}{detail}",
        # "on disk" was a lie in the place it mattered most: a fresh clone has
        # no frameworks/raw/ at all, so a hands-off session read 133 available
        # and went looking for material that was never going to be there.
        f"  Source library (ledger)   : {res['writable']} frameworks with prose, "
        f"{res['needs_prose']} needing extraction — only on a machine that has "
        "frameworks/raw/",
        f"  Fact sheets (committed)   : {_fact_txt(r)} — what a fresh clone can "
        "write from",
        f"  Floors                    : {WARN_DAYS} days per channel, "
        f"{RESERVE_FLOOR} frameworks in reserve, {FACTSHEET_FLOOR} fact sheets",
    ])


def short(r: dict) -> list[str]:
    """Everything below its floor: the two publishing channels, and the reserve.

    An unmeasured channel is never 'short'. The token branch in `report` already
    fails hard on a token that is set and broken, so unmeasured here only means
    nobody asked for that channel — reporting it as zero would fail every run in
    any environment without secrets, and reporting it as healthy would rebuild
    the silent success this whole check exists to kill."""
    out = []
    if r["instagram_days"] < WARN_DAYS:
        out.append(f"Instagram: {r['instagram_days']} days of carousels queued")
    if r["x_threads_days"] is not None and r["x_threads_days"] < WARN_DAYS:
        out.append(f"X/Threads: {r['x_threads_days']} days of framework drafts left")
    writable = r["reserve"].get("writable", 0)
    if writable < RESERVE_FLOOR:
        out.append(
            f"Reserve: only {writable} frameworks left with prose on disk "
            f"({r['reserve'].get('needs_prose', 0)} more need extracting from the "
            "source PDFs first) — see frameworks/README.md")
    # Absent means unmeasured, the same courtesy the Notion channel gets above:
    # a caller that did not ask for this number must not be told it is zero.
    if r.get("factsheets") is not None and r["factsheets"] < FACTSHEET_FLOOR:
        out.append(
            f"Fact sheets: only {r['factsheets']} unwritten fact sheets committed — "
            "a session with frameworks/raw/ has to top them up, or the auto-producer "
            "wakes with nothing to write from (see frameworks/AUTOPRODUCER.md)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 when a channel is below the floor")
    args = ap.parse_args()

    r = report()
    print(render(r))
    if not args.check:
        return

    problems = short(r)
    if not problems:
        print(f"\nOK — every measured channel is above the {WARN_DAYS}-day floor, "
              f"with {r['reserve']['writable']} frameworks in reserve.")
        return
    print("\nRUNWAY SHORT:")
    for p in problems:
        print(f"  - {p}")
    print("\nWrite the next batch. frameworks/next.md ranks what to write, and "
          "each framework needs all three files: units/<slug>.md, "
          "carousels/<slug>.json, and ten queries in assets/background_queries.json.")
    sys.exit(1)


if __name__ == "__main__":
    main()
