from core.analysis import (
    DataPoint,
    best_content_types,
    best_hook,
    best_slots,
    engagement_rate,
    ranked,
)


def test_engagement_rate():
    assert engagement_rate(2, 1, 1, 100) == 0.04
    assert engagement_rate(1, 0, 0, 0) is None


def test_datapoint_rate():
    p = DataPoint(impressions=200, likes=4, replies=2, reposts=2)
    assert p.engagement_rate == 0.04
    assert DataPoint(impressions=0, likes=5).engagement_rate is None


def _pts():
    return [
        DataPoint(slot="07:30", content_type="Thread", hook="A", impressions=100, likes=1),   # 1%
        DataPoint(slot="07:30", content_type="Thread", hook="A", impressions=100, likes=3),   # 3%
        DataPoint(slot="21:30", content_type="反共識", hook="B", impressions=100, likes=10),  # 10%
        DataPoint(slot="12:30", content_type="反共識", hook="B", impressions=100, likes=0),   # 0%
    ]


def test_ranked_sorted_desc():
    rows = ranked(_pts(), lambda p: p.slot)
    assert rows[0][0] == "21:30"


def test_best_slots_top():
    assert best_slots(_pts(), top=2) == ["21:30", "07:30"]


def test_best_hook():
    assert best_hook(_pts()) == "B"


def test_best_content_types():
    types = best_content_types(_pts())
    assert types[0] == "反共識"


def test_zero_impression_points_ignored():
    pts = [DataPoint(slot="07:30", impressions=0, likes=99)]
    assert ranked(pts, lambda p: p.slot) == []
