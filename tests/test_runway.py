"""The runway meter, and the ledger checks that keep it honest.

Every assertion here traces to a way the pipeline has actually gone quiet
without anything turning red.
"""
from __future__ import annotations

import csv
import os
from pathlib import Path

import subprocess
import sys

import pytest

from scripts import build_framework_index, next_frameworks, runway

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
    healthy_reserve = {"writable": runway.RESERVE_FLOOR, "needs_prose": 0}
    r = {"instagram_days": 30, "x_threads_days": None,
         "notion_drafts": None, "pending_inserts": 0, "reserve": healthy_reserve}
    assert runway.short(r) == []
    assert "unmeasured" in runway.render(r)


def test_a_short_channel_is_named(monkeypatch):
    r = {"instagram_days": 2, "x_threads_days": 40, "notion_drafts": 40,
         "pending_inserts": 0,
         "reserve": {"writable": runway.RESERVE_FLOOR, "needs_prose": 0}}
    problems = runway.short(r)
    assert len(problems) == 1 and "Instagram" in problems[0]


def test_a_draining_reserve_is_flagged_long_before_it_bites():
    """63 frameworks exist only as contents-page entries because the Drive
    reader truncates each PDF around page 80. The day the writable pile empties
    is the day the shortlist comes back blank, and by then extracting them is
    urgent. Two batches of warning is months at one post a day."""
    r = {"instagram_days": 30, "x_threads_days": 30, "notion_drafts": 30,
         "pending_inserts": 0,
         "reserve": {"writable": runway.RESERVE_FLOOR - 1, "needs_prose": 63}}
    problems = runway.short(r)
    assert len(problems) == 1 and "Reserve" in problems[0]
    assert runway.RESERVE_FLOOR >= 2 * runway.BATCH_DAYS


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
    source text that was never extracted.

    Checked against the ledger, not the filesystem: frameworks/raw/ is
    gitignored, so a filesystem check passes only on the machine that ran the
    ingest and fails everywhere else. A distilled provenance tier is written
    only when a brief was present at build time, so it carries the same fact
    into checkouts that will never have the prose."""
    for row in next_frameworks.build()["shortlist"]:
        assert row["source"] == "brief", row["slug"]
        assert row["provenance"], row["slug"]


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


# ── the two ways this system broke on its first CI run ───────────────────────

def _outside_repo() -> str:
    """Run from somewhere that is not the repo, so a pass cannot be the current
    working directory quietly doing the work."""
    import tempfile
    return tempfile.gettempdir()


def test_ranking_never_reads_the_gitignored_briefs(monkeypatch):
    """Nothing under frameworks/raw/ may be touched while ranking.

    That directory is gitignored — it holds verbatim book prose and never gets
    published — so a ranker that reads it scores every framework at zero
    anywhere but the machine that ran the ingest. On this system's first CI run
    that is exactly what happened, and the cron committed the zeroed list as
    the shortlist. The scoring inputs live in the ledger for this reason."""
    real_read = Path.read_text
    raw = (BASE / "frameworks" / "raw").resolve()

    def guarded(self, *a, **kw):
        if raw in self.resolve().parents:
            raise AssertionError(f"ranking read a gitignored brief: {self}")
        return real_read(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", guarded)
    shortlist = next_frameworks.build()["shortlist"]
    assert len(shortlist) == next_frameworks.SHORTLIST
    assert any(r["score"] > 0 for r in shortlist), (
        "every score is zero — the ledger is missing its distilled columns")


def test_index_builder_refuses_to_run_without_the_briefs(tmp_path, monkeypatch):
    """Rewriting the ledger from an empty frameworks/raw/ would mark all 102
    writable frameworks as contents-page-only and blank every provenance tier —
    erasing the record this ledger exists to keep."""
    monkeypatch.setattr(build_framework_index, "RAW_DIR", tmp_path / "empty")
    with pytest.raises(SystemExit):
        build_framework_index.build()


def test_runway_runs_as_a_standalone_file():
    """`python scripts/runway.py` puts scripts/ on sys.path, not the repo root,
    so `from services.notion import ...` died with ModuleNotFoundError — and
    only on a machine holding a NOTION_TOKEN, which is CI and never a laptop."""
    script = str(BASE / "scripts" / "runway.py")
    env = {**os.environ, "NOTION_TOKEN": ""}

    proc = subprocess.run([sys.executable, script], capture_output=True,
                          text=True, cwd=_outside_repo(), env=env)
    assert proc.returncode == 0, proc.stderr
    assert "Content runway" in proc.stdout

    # The branch the CLI run never reaches without a token: executing the file
    # has to leave the repo root importable.
    probe = subprocess.run(
        [sys.executable, "-c",
         f"import runpy; runpy.run_path({script!r}, run_name='probe'); "
         "import services.notion"],
        capture_output=True, text=True, cwd=_outside_repo(), env=env)
    assert probe.returncode == 0, probe.stderr


# ── the fact sheets: the only reserve a fresh clone can spend ────────────────

FACTSHEETS = BASE / "frameworks" / "factsheets"


def test_factsheets_stop_counting_once_their_framework_ships(tmp_path, monkeypatch):
    """The number has to answer "how much can a fresh clone write today", not
    "how many files are in the folder" — otherwise it reads full forever."""
    sheets, units = tmp_path / "factsheets", tmp_path / "units"
    sheets.mkdir(); units.mkdir()
    for name in ("alpha", "beta", "gamma"):
        (sheets / f"{name}.md").write_text("x", encoding="utf-8")
    (units / "beta.md").write_text("x", encoding="utf-8")   # already shipped
    monkeypatch.setattr(runway, "FACTSHEETS", sheets)
    monkeypatch.setattr(runway, "UNITS", units)
    assert runway.factsheets_available() == 2


def test_an_empty_factsheet_shelf_is_flagged():
    """The auto-producer has no Notion access and no frameworks/raw/ — it can
    only write from committed fact sheets. Four consecutive Routine fires
    produced nothing because that shelf was empty and nothing said so."""
    r = {"instagram_days": 30, "x_threads_days": 30, "notion_drafts": 30,
         "pending_inserts": 0,
         "reserve": {"writable": 100, "needs_prose": 0},
         "factsheets": 0}
    problems = runway.short(r)
    assert len(problems) == 1 and "Fact sheets" in problems[0]


def test_a_missing_factsheet_count_is_unmeasured_not_empty():
    r = {"instagram_days": 30, "x_threads_days": 30, "notion_drafts": 30,
         "pending_inserts": 0, "reserve": {"writable": 100, "needs_prose": 0}}
    assert runway.short(r) == []


def test_the_factsheet_floor_is_a_whole_batch():
    """Topping up fact sheets needs a session that has frameworks/raw/, which
    is not something the cron can summon. The warning therefore has to arrive
    while a full batch is still in hand, not when the shelf is nearly bare."""
    assert runway.FACTSHEET_FLOOR >= runway.BATCH_DAYS


def test_every_factsheet_declares_a_provenance_tier():
    """The series is sold on provenance, so the tier is a ceiling on how the
    authority hook may be written — `firm` alone permits naming McKinsey, BCG
    or Bain. A sheet without one invites the writer to guess."""
    tiers = {"firm", "author", "dated", "none"}
    bad = []
    for p in sorted(FACTSHEETS.glob("*.md")):
        line = next((ln for ln in p.read_text("utf-8").splitlines()
                     if ln.startswith("- provenance:")), None)
        if line is None or line.split(":", 1)[1].strip() not in tiers:
            bad.append(p.name)
    assert not bad, f"fact sheet(s) with no usable provenance tier: {bad}"


def test_the_autoproducer_orders_exist_and_point_at_the_factsheets():
    """The Routine's prompt is three lines that defer to this file. If it goes
    missing the Routine has no rules at all, which is how the prompt drifted
    out of sync with the pipeline in the first place."""
    orders = (BASE / "frameworks" / "AUTOPRODUCER.md").read_text("utf-8")
    assert "frameworks/factsheets/" in orders
    assert "H-002" in orders and "H-005" in orders, (
        "both live experiments have to be stated where the writer will read them")
