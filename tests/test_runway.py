"""The runway meter, and the ledger checks that keep it honest.

Every assertion here traces to a way the pipeline has actually gone quiet
without anything turning red.
"""
from __future__ import annotations

import csv
from pathlib import Path

from scripts import next_frameworks, runway

BASE = Path(__file__).resolve().parent.parent


# ── the meter ────────────────────────────────────────────────────────────────

def test_queue_depth_ignores_comments_and_blanks(tmp_path, monkeypatch):
    q = tmp_path / "queue.txt"
    q.write_text("# a comment\n\nporter\n  \nfive-forces\n", encoding="utf-8")
    monkeypatch.setattr(runway, "QUEUE", q)
    assert runway.queue_depth() == 2


def test_missing_queue_reads_as_empty_not_as_healthy(tmp_path, monkeypatch):
    monkeypatch.setattr(runway, "QUEUE", tmp_path / "nope.txt")
    assert runway.queue_depth() == 0


def test_pending_inserts_excludes_numbered_essays(tmp_path, monkeypatch):
    units, ledger = tmp_path / "units", tmp_path / "ledger.txt"
    units.mkdir()
    for name in ("porter.md", "127.md", "201.md", "value-chain.md"):
        (units / name).write_text("x", encoding="utf-8")
    ledger.write_text("porter\n", encoding="utf-8")
    monkeypatch.setattr(runway, "UNITS", units)
    monkeypatch.setattr(runway, "LEDGER", ledger)
    # value-chain only: the numbered essays run on a different pipeline and
    # POST_FRAMEWORKS_ONLY filters them out, so counting them as runway is the
    # exact miscount that made an empty framework queue look full.
    assert runway.pending_inserts() == 1


def test_unmeasured_channel_is_never_reported_as_short(monkeypatch):
    """No Notion token means the channel is unknown, not fine and not broken.

    Reporting `0 days` there would fail the job every day in any environment
    without secrets; reporting it as healthy would be the silent success this
    whole check exists to kill. It reports neither."""
    r = {"instagram_days": 30, "x_threads_days": None,
         "notion_drafts": None, "pending_inserts": 0, "reserve": {}}
    assert runway.short(r) == []
    assert "unmeasured" in runway.render({**r, "reserve": {"writable": 1, "needs_prose": 2}})


def test_a_short_channel_is_named(monkeypatch):
    r = {"instagram_days": 2, "x_threads_days": 40,
         "notion_drafts": 40, "pending_inserts": 0, "reserve": {}}
    problems = runway.short(r)
    assert len(problems) == 1 and "Instagram" in problems[0]


def test_the_floor_and_the_batch_size_are_a_workable_pair():
    """A batch has to clear the floor with room to spare.

    If a standard batch only just reaches the floor, the alarm fires again the
    day after every batch is written. That alarm gets muted, and a muted alarm
    is worse than no alarm because it still looks like coverage. It also has to
    be a real week of notice against a one-a-day schedule."""
    assert runway.WARN_DAYS >= 5
    assert runway.BATCH_DAYS >= 2 * runway.WARN_DAYS
    assert runway.BATCH_DAYS == next_frameworks.SHORTLIST, (
        "the shortlist is what someone writes when the alarm fires, so it has "
        "to be the batch the floor was sized against")


# ── the ledger the meter reads ───────────────────────────────────────────────

def _index_rows():
    with (BASE / "frameworks" / "index.csv").open(encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def test_every_published_unit_is_recorded_in_the_ledger():
    """A unit missing from UNIT_SLUGS counts as backlog forever.

    That is how the ledger drifted the first time: index.csv described a
    library of eight while twelve frameworks had shipped, so the obvious read
    of the repo was that the backlog was nearly spent."""
    written = {p.stem for p in (BASE / "units").glob("*.md") if not p.stem.isdigit()}
    recorded = {r["unit"] for r in _index_rows() if r["unit"]}
    assert not written - recorded, (
        f"unit(s) absent from frameworks/index.csv: {sorted(written - recorded)} — add "
        "them to UNIT_SLUGS in scripts/build_framework_index.py and rerun it, or the "
        "runway meter will keep counting them as unwritten."
    )


def test_the_ledger_does_not_claim_units_that_do_not_exist():
    recorded = {r["unit"] for r in _index_rows() if r["unit"]}
    missing = {u for u in recorded if not (BASE / "units" / f"{u}.md").exists()}
    assert not missing, f"index.csv points at missing units: {sorted(missing)}"


def test_every_queued_carousel_has_a_spec():
    """A queued slug with no spec drips nothing and dequeues anyway, so the
    queue reads as deeper than it is."""
    queued = [ln.strip() for ln in (BASE / "queue" / "carousel_queue.txt")
              .read_text("utf-8").splitlines()
              if ln.strip() and not ln.lstrip().startswith("#")]
    missing = [s for s in queued if not (BASE / "carousels" / f"{s}.json").exists()]
    assert not missing, f"queued with no carousels/<slug>.json: {missing}"


# ── the shortlist ────────────────────────────────────────────────────────────

def test_shortlist_only_offers_frameworks_with_prose_on_disk():
    """Ranking a contents-page entry would send whoever picks it up looking for
    source text that was never extracted."""
    data = next_frameworks.build()
    for row in data["shortlist"]:
        assert row["source"] == "brief", row["slug"]
        assert (BASE / "frameworks" / "raw" / f"{row['slug']}.md").exists()


def test_shortlist_spreads_across_categories():
    """Scoring once and taking the top N lets a category with a deep bench
    sweep the list, which produces a batch of six posts from one book."""
    data = next_frameworks.build()
    cats = {r["category"] for r in data["shortlist"]}
    assert len(cats) >= 5, f"shortlist covers only {sorted(cats)}"


def test_shortlist_is_deterministic():
    assert next_frameworks.build()["shortlist"] == next_frameworks.build()["shortlist"]


def test_committed_shortlist_is_current():
    assert (BASE / "frameworks" / "next.md").read_text("utf-8") == \
        next_frameworks.render(next_frameworks.build())


def test_measured_performance_stays_out_until_the_corpus_can_carry_it():
    """Same discipline the retro tester applies: no verdict on thin arms."""
    assert next_frameworks.MIN_PER_CATEGORY >= 5
