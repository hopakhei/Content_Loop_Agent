"""A scheduled run that never happens leaves nothing behind to find.

The five-hour runner shortage on 2026-08-06 cancelled seven runs and left seven
red entries, which is the easy case. The harder one is already routine here: the
DM loop is scheduled 48 times a day and lands about 24, and the missing ones
produce no run, no log and no notification. Nothing in the repository could see
that until this check existed.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import job_health as jh  # noqa: E402


def test_floor_is_half_the_expected_count():
    assert jh.floor_for(48) == 24
    assert jh.floor_for(2) == 1


def test_a_daily_job_that_did_not_run_is_always_short():
    """Half of one rounds to zero, and zero would make every daily workflow
    unfailable — which is the whole set of publishing jobs."""
    assert jh.floor_for(1) == 1
    assert jh.short({"post.yml": {"runs": 0, "failed": 0}})


def test_routine_dropping_does_not_fire():
    """GitHub drops scheduled runs constantly. An alarm at the full count would
    fire most days and get muted."""
    assert not jh.short({w: {"runs": jh.EXPECTED_PER_DAY[w], "failed": 0}
                         for w in jh.EXPECTED_PER_DAY})
    assert not jh.short({"instagram-dm.yml": {"runs": 30, "failed": 0}})


def test_half_the_dm_loop_missing_fires():
    assert jh.short({"instagram-dm.yml": {"runs": 12, "failed": 0}})


def test_a_workflow_that_ran_but_failed_every_time_fires():
    """Enough runs, all of them bad, is not health — and the run count alone
    would call it healthy."""
    problems = jh.short({"learn.yml": {"runs": 1, "failed": 1}})
    assert problems and "failed" in problems[0]


def test_partial_failure_does_not_fire():
    """Seven bad runs out of fifty is the 2026-08-06 shortage, which cleared on
    its own. Firing on that would report an outage GitHub already fixed."""
    assert not jh.short({"instagram-dm.yml": {"runs": 41, "failed": 7}})


def test_an_unreadable_workflow_is_never_reported_as_short():
    """Same rule as the runway check: unmeasured is not zero. A token that
    cannot read Actions must not invent an outage."""
    assert not jh.short({"post.yml": {"runs": None, "failed": None,
                                      "error": "403"}})


def test_every_scheduled_workflow_is_covered():
    """A new cron with no entry here is a job nobody is watching."""
    import re
    wf_dir = Path(__file__).resolve().parent.parent / ".github" / "workflows"
    scheduled = {p.name for p in wf_dir.glob("*.yml")
                 if re.search(r"^\s*schedule:", p.read_text("utf-8"), re.M)}
    assert scheduled == set(jh.EXPECTED_PER_DAY), (
        f"unwatched: {sorted(scheduled - set(jh.EXPECTED_PER_DAY))}; "
        f"stale: {sorted(set(jh.EXPECTED_PER_DAY) - scheduled)}"
    )
