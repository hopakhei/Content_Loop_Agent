"""The 貼地 rule, enforced where it can actually stop something.

Every post on every channel has to start where the reader stands and travel
through a scene they live in. That rule was written down in three skill files,
which binds whoever reads a skill file — and none of the three publishing crons
reads one. Between the rule being written and this test existing, twelve units
shipped with a scene in four of them.

The grading is deliberately split: content that has already gone out is
reported but never fails the build, because an alarm that can never be silenced
gets muted, and a muted alarm is worse than none.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import audit_grounding as ag  # noqa: E402


def test_everything_still_publishable_is_grounded():
    rows = ag.report()
    pending = ag.pending_slugs()
    bad = sorted(r["slug"] for r in rows if r["slug"] in pending and not r["ok"])
    assert not bad, (
        f"not grounded, and still publishable: {bad} — see 鐵律零點六 in "
        ".claude/skills/x-post/SKILL.md, or run python scripts/audit_grounding.py"
    )


def test_a_date_opening_is_not_grounded():
    """The most common way this broke: the framework's history goes first and
    the reader goes second."""
    assert not ag.grounded_opening("1937 年，一位經濟學家問了一條怪問題")
    assert not ag.grounded_opening("1990 年代末，所有人都說世界是平的")


def test_provenance_later_in_the_sentence_is_fine():
    """The rule moves the year, it does not delete it — this series is sold on
    its provenance and a check that forbade dates would cost more than it saves."""
    assert ag.grounded_opening("你買的那間公司營收翻倍，2008 年的獲利公式說它可能正在缺現金")


def test_the_reader_has_to_be_in_the_opening_clause_not_after_the_dash():
    """Threads truncates the feed preview, so a 你 in the second clause is a 你
    most readers never reach."""
    assert not ag.grounded_opening("「這是我們的核心業務」——你聽到這句話的時候")
    assert ag.grounded_opening("你聽到「這是我們的核心業務」這句話的時候")


def test_an_everyday_scene_counts_even_without_the_reader():
    assert ag.grounded_opening("巷口那間早餐店排隊最長")


def test_a_boardroom_opening_does_not_count():
    assert not ag.grounded_opening("董事會需要一把刀，把核心兩個字定義清楚")


@pytest.mark.parametrize("channel", ["body_life", "deck_life", "caption_life"])
def test_the_audit_covers_all_three_channels(channel):
    """X/Threads, Instagram slides, Instagram caption. A check that graded only
    the unit files would have passed the batch whose carousels had no scene."""
    row = ag.audit("jobs-to-be-done")
    assert channel in row
