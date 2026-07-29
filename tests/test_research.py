"""Guards on the research loop.

The failure mode this is defending against is not a crash. It is a plausible
number: a hypothesis card that declares a winner from three observations, a
retro run that quietly upgrades itself to a verdict it has no right to, an arm
assignment that silently swallows rows it could not classify. Every one of those
produces output that looks exactly like a result.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from research import cards, scorers
from scripts import retro_test

BASE = Path(__file__).resolve().parent.parent

GOOD = """---
id: H-999
status: open
source: own-metrics
claim: test
variable:
  key: k
  scorer: authority_line1
prediction:
  metric: impressions
  direction: yes > no
  min_effect: 1.5
  n_per_arm: 10
---
body
"""


def _card(**overrides):
    text = GOOD
    for old, new in overrides.items():
        text = text.replace(old, new)
    return text


# ── card validation ──────────────────────────────────────────────────────────

def test_a_valid_card_parses():
    h = cards.parse_card(GOOD, Path("H-999.md"))
    assert h.prediction.high_arm == "yes" and h.prediction.low_arm == "no"


def test_min_effect_must_exceed_one():
    """An effect too small to act on is not worth weeks of posting slots, and a
    card that admits any effect at all will always find one."""
    with pytest.raises(ValueError, match="min_effect"):
        cards.parse_card(_card(**{"min_effect: 1.5": "min_effect: 1.0"}), Path("H-999.md"))


def test_a_card_without_a_stopping_rule_is_rejected():
    with pytest.raises(ValueError, match="n_per_arm"):
        cards.parse_card(_card(**{"  n_per_arm: 10\n": ""}), Path("H-999.md"))


def test_unknown_scorer_is_rejected_at_load_time():
    """Not at run time, where it would surface as an empty comparison."""
    with pytest.raises(KeyError, match="unknown scorer"):
        cards.parse_card(_card(**{"authority_line1": "does_not_exist"}), Path("H-999.md"))


def test_shipped_cards_all_parse():
    ids = [h.id for h in cards.load_all()]
    assert ids == sorted(ids) and len(ids) == len(set(ids))


# ── scorers ──────────────────────────────────────────────────────────────────

def test_unscorable_rows_are_dropped_not_defaulted():
    """None must not collapse into the negative arm — that would invent data."""
    assert scorers.authority_line1({"text": ""}) is None
    assert scorers.authority_line1({}) is None
    assert scorers.x_link_arm({"tags": {}}) is None


def test_authority_reads_only_the_first_line():
    row = {"text": "一間正在賺錢的公司，可能已經在死。\n1970 年，BCG 創辦人 Bruce Henderson 畫了一張表。"}
    assert scorers.authority_line1(row) == "no"
    assert scorers.authority_anywhere(row) == "yes"


# ── text reconstruction ──────────────────────────────────────────────────────

def test_text_is_read_as_of_the_post_date_not_from_the_working_tree():
    """units/*.md were rewritten after most framework posts had gone out. Using
    the current file scores wording the audience never saw."""
    row = {"slug": "bcg-matrix", "hook": "A", "posted_at": "2026-07-26T23:49:00Z"}
    cards.hydrate([row])
    if row["text"] is None:
        pytest.skip("no git history for units/bcg-matrix.md in this checkout")
    assert row["text_source"] == "git-history"
    assert scorers.authority_line1(row) == "no"


def test_missing_history_yields_no_text_rather_than_current_text():
    row = {"slug": "bcg-matrix", "hook": "A", "posted_at": "2001-01-01T00:00:00Z"}
    cards.hydrate([row])
    assert row["text"] is None


# ── metrics ──────────────────────────────────────────────────────────────────

def test_zero_and_missing_impressions_are_both_unmeasured():
    """A stored 0 is a failed metrics fetch, not an observation of nobody. X has
    a run of 22 consecutive rows like that."""
    assert retro_test.metric_value({"impressions": 0, "likes": 1}, "impressions") is None
    assert retro_test.metric_value({"impressions": None, "likes": 1}, "impressions") is None
    assert retro_test.metric_value({"impressions": 100, "likes": 1}, "engagement_rate") == 0.01


# ── verdicts ─────────────────────────────────────────────────────────────────

def _rows(arm_values, platform="Threads", start_day=1):
    return [
        {"platform": platform, "impressions": v, "likes": 0, "replies": 0, "reposts": 0,
         "posted_at": f"2026-07-{start_day + i:02d}T12:00:00Z", "tags": {"x_link_arm": arm}}
        for arm, vals in arm_values.items()
        for i, v in enumerate(vals)
    ]


def _hyp(**over):
    return cards.parse_card(
        _card(**{"authority_line1": "x_link_arm", "direction: yes > no": "direction: link > no_link",
                 "n_per_arm: 10": f"n_per_arm: {over.get('n_per_arm', 2)}"}),
        Path("H-999.md"))


def test_retro_never_returns_supported():
    """Observational data cannot close a hypothesis, however large the effect.
    The only vocabulary available here tops out at `retro-supports`."""
    h = _hyp()
    res = retro_test.evaluate(h, _rows({"link": [1000, 1100, 1200], "no_link": [10, 11, 12]}))
    assert res["verdict"] == "retro-supports"
    assert all(r["verdict"] != "supported" for r in [res])


def test_thin_arms_never_produce_a_winner():
    h = cards.parse_card(
        _card(**{"authority_line1": "x_link_arm", "direction: yes > no": "direction: link > no_link"}),
        Path("H-999.md"))          # n_per_arm 10
    res = retro_test.evaluate(h, _rows({"link": [1000, 1100], "no_link": [10, 11]}))
    assert res["verdict"] == "still-thin"


def test_an_effect_below_min_effect_is_not_a_win():
    h = _hyp()
    res = retro_test.evaluate(h, _rows({"link": [100] * 6, "no_link": [95] * 6}))
    assert res["verdict"] in {"below-min-effect", "inconclusive"}


def test_single_valued_variable_reports_no_variation():
    h = _hyp()
    res = retro_test.evaluate(h, _rows({"link": [100, 200, 300]}))
    assert res["verdict"] == "no-variation"


def test_non_concurrent_arms_raise_a_confound_warning():
    """The check the X link A/B needed: one arm stopped being assigned while the
    other kept accruing rows through a period when the account itself changed."""
    rows = _rows({"link": [10, 11, 12]}, start_day=1) + _rows({"no_link": [20, 21, 22]}, start_day=20)
    res = retro_test.evaluate(_hyp(), rows)
    assert any("overlap in time" in w for w in res["warnings"])


def test_concurrent_arms_raise_no_warning():
    rows = _rows({"link": [10, 11, 12]}, start_day=1) + _rows({"no_link": [20, 21, 22]}, start_day=1)
    assert not retro_test.evaluate(_hyp(), rows)["warnings"]


# ── the snapshot ─────────────────────────────────────────────────────────────

def test_snapshot_rows_carry_what_the_scorers_need():
    path = max((BASE / "research" / "snapshots").glob("*.json"), key=lambda p: p.name)
    rows = json.loads(path.read_text("utf-8"))["rows"]
    assert rows
    for r in rows:
        assert r["platform"] and r["posted_at"]
        assert r["impressions"] is None or isinstance(r["impressions"], (int, float))


# ── live experiment assignment ───────────────────────────────────────────────

class _Draft:
    def __init__(self, ident, hooks):
        self.id, self.hooks = ident, hooks

    def available_hooks(self):
        return {k: v for k, v in self.hooks.items() if v}


BOTH = {"A": "這間公司的毛利在倒數。", "B": "馬戲團裡沒有動物，票價卻更高。"}


def _h002():
    from research import experiments
    h = next(h for h in cards.load_all() if h.id == "H-002")
    assert experiments.eligible(_Draft("x", BOTH), h)
    return h


def test_exactly_one_experiment_is_live():
    from research import experiments
    assert experiments.active() is not None          # H-002


def test_two_live_experiments_are_rejected():
    """Two concurrent tests quarter every cell; the registry refuses rather than
    letting both run and settle neither."""
    from research import experiments
    live = [h for h in cards.load_all() if h.status == "testing"]
    with pytest.raises(ValueError, match="more than one"):
        experiments.active(live * 2)


def test_a_draft_that_cannot_carry_both_arms_sits_out():
    """Checking only the drawn arm would let such a unit feed one side only, so
    the arm difference would partly be a unit difference."""
    from research import experiments
    one_sided = _Draft("y", {"A": "這間公司的毛利在倒數。", "B": "這間公司的估值太貴。"})
    assert not experiments.eligible(one_sided, _h002())
    assert experiments.assign(one_sided, "Threads", _h002(), day="2026-08-01") is None


def test_assignment_is_stable_within_a_day_and_moves_across_days():
    """Stable so a retried slot cannot switch arms; moving so a framework is not
    pinned to one arm for the whole run."""
    from research import experiments
    h, d = _h002(), _Draft("porter", BOTH)
    days = [f"2026-08-{i:02d}" for i in range(1, 21)]
    arms = [experiments.assign(d, "Threads", h, day=x).arm for x in days]
    assert experiments.assign(d, "Threads", h, day=days[0]).arm == arms[0]
    assert len(set(arms)) == 2, "the same draft never changed arm across 20 days"


def test_assignment_respects_the_cards_platform():
    from research import experiments
    h, d = _h002(), _Draft("porter", BOTH)
    assert experiments.assign(d, "Threads", h, day="2026-08-01") is not None
    assert experiments.assign(d, "X", h, day="2026-08-01") is None


def test_the_arm_tag_lands_on_the_performance_row():
    from research import experiments
    a = experiments.assign(_Draft("porter", BOTH), "Threads", _h002(), day="2026-08-01")
    assert a.tag == {"h002_arm": a.arm}


def test_enough_units_can_carry_both_arms_to_finish_the_run():
    """A starved experiment looks like a running one. It never reaches n."""
    from pathlib import Path
    from core.parsing import parse_units
    from research import experiments
    h = _h002()
    ok = sum(
        experiments.eligible(_Draft(p.stem, parse_units(p.read_text("utf-8"))[0].hooks), h)
        for p in Path("units").glob("*.md") if not p.stem.isdigit()
    )
    assert ok >= 8, f"only {ok} units can carry both arms of {h.id}"


# ── digest guards ────────────────────────────────────────────────────────────

def test_digest_refuses_to_report_an_arm_that_stopped_being_assigned():
    from loops.learn_loop import _ab_line, _arm_last_seen
    rows = [{"tags": {"x_link_arm": "link"}, "posted_at": "2026-07-19T05:00:00Z"},
            {"tags": {"x_link_arm": "no_link"}, "posted_at": "2026-07-28T05:00:00Z"}]
    line = _ab_line("X link A/B", [("no_link", 0.0065, 28), ("link", 0.0, 15)],
                    _arm_last_seen(rows, "x_link_arm"))
    assert "STALE" in line and "0.65%" not in line


def test_digest_reports_concurrent_arms_normally():
    from loops.learn_loop import _ab_line, _arm_last_seen
    rows = [{"tags": {"x_link_arm": "link"}, "posted_at": "2026-07-27T05:00:00Z"},
            {"tags": {"x_link_arm": "no_link"}, "posted_at": "2026-07-28T05:00:00Z"}]
    line = _ab_line("X link A/B", [("no_link", 0.0065, 28), ("link", 0.0, 15)],
                    _arm_last_seen(rows, "x_link_arm"))
    assert "0.65%" in line and "STALE" not in line


def test_hook_winner_is_reported_with_its_sample_size_and_margin():
    """A 3x lead and a 0.02% lead used to print identically."""
    from loops.learn_loop import _hook_line
    line = _hook_line({"Threads": [("A", 0.0048, 12), ("B", 0.0031, 9)]})
    assert "n=12" in line and "1.55x" in line
