from datetime import datetime
from zoneinfo import ZoneInfo

from core.models import Article, Draft
from core.selection import can_post_on_x, matches_slot, select_draft

HKT = ZoneInfo("Asia/Hong_Kong")
REF = datetime(2026, 6, 30, 12, 30, tzinfo=HKT)


def _draft(id, **kw):
    return Draft(id=id, **kw)


def test_eligibility_x_only():
    assert can_post_on_x(_draft("a", platforms=["X"]))
    assert can_post_on_x(_draft("a", platforms=[]))
    assert not can_post_on_x(_draft("a", platforms=["Threads"]))


def test_matches_slot_date_only_today():
    d = _draft("a", scheduled_date={"start": "2026-06-30", "is_datetime": False})
    assert matches_slot(d, "12:30", REF)


def test_matches_slot_datetime_near():
    d = _draft("a", scheduled_date={"start": "2026-06-30T12:35:00+08:00", "is_datetime": True})
    assert matches_slot(d, "12:30", REF)
    far = _draft("b", scheduled_date={"start": "2026-06-30T18:30:00+08:00", "is_datetime": True})
    assert not matches_slot(far, "12:30", REF)


def test_matches_slot_other_day():
    d = _draft("a", scheduled_date={"start": "2026-07-01", "is_datetime": False})
    assert not matches_slot(d, "12:30", REF)


def test_priority_scheduled_slot_wins():
    slotted = _draft("s", status="Scheduled", platforms=["X"],
                     scheduled_date={"start": "2026-06-30T12:30:00+08:00", "is_datetime": True})
    other = _draft("o", status="Scheduled", platforms=["X"], argument_num=1)
    chosen, reason = select_draft("12:30", REF, [slotted, other], [], {}, {})
    assert chosen.id == "s" and reason == "scheduled-slot"


def test_round_robin_prefers_fewest_posted_article():
    a1 = _draft("a1", status="Scheduled", platforms=["X"], article_id="A", argument_num=1)
    a2 = _draft("a2", status="Scheduled", platforms=["X"], article_id="B", argument_num=1)
    articles = {"A": Article(id="A"), "B": Article(id="B")}
    chosen, reason = select_draft("12:30", REF, [a1, a2], [], {"A": 3, "B": 0}, articles)
    assert chosen.article_id == "B" and reason == "round-robin"


def test_round_robin_respects_target_per_day():
    a1 = _draft("a1", status="Scheduled", platforms=["X"], article_id="A", argument_num=1)
    a2 = _draft("a2", status="Scheduled", platforms=["X"], article_id="B", argument_num=1)
    # B already hit its target of 1; A has posted more but is under no cap.
    articles = {"A": Article(id="A", target_per_day=10), "B": Article(id="B", target_per_day=1)}
    chosen, _ = select_draft("12:30", REF, [a1, a2], [], {"A": 2, "B": 1}, articles)
    assert chosen.article_id == "A"


def test_draft_status_argument_order():
    d2 = _draft("d2", status="Draft", platforms=["X"], argument_num=2)
    d1 = _draft("d1", status="Draft", platforms=["X"], argument_num=1)
    chosen, reason = select_draft("12:30", REF, [], [d2, d1], {}, {})
    assert chosen.id == "d1" and reason == "argument-order"


def test_threads_only_excluded():
    d = _draft("t", status="Draft", platforms=["Threads"], argument_num=1)
    chosen, reason = select_draft("12:30", REF, [], [d], {}, {})
    assert chosen is None and reason == "no-eligible-drafts"
