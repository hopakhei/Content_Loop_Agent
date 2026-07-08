"""Loop 2 metric refresh: platform routing + refresh window, with fake services."""
from datetime import datetime, timedelta, timezone

from config.schema import Performance
from loops import learn_loop


def _iso(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def _row(pid, platform, hours_ago, impressions=0.0):
    return {
        "page_id": f"page-{pid}",
        "post_id": pid,
        "draft_id": "d1",
        "posted_at": _iso(hours_ago),
        "platform": platform,
        "hook_used": "A - 反共識",
        "content_type": "反共識",
        "impressions": impressions,
        "likes": 0.0,
        "replies": 0.0,
        "reposts": 0.0,
        "link_clicks": 0.0,
    }


class FakeNotion:
    def __init__(self, rows):
        self._rows = rows
        self.updates = {}

    def get_performance_rows(self, since_days=30):
        return self._rows

    def update_performance_metrics(self, page_id, metrics):
        self.updates[page_id] = metrics

    def get_next_loop_iteration(self):
        return 1

    def write_rules(self, **kwargs):
        return True


class FakeTwitter:
    def __init__(self, metrics):
        self.requested = []
        self._metrics = metrics

    def get_metrics(self, ids):
        self.requested.extend(ids)
        return {i: self._metrics[i] for i in ids if i in self._metrics}


class FakeThreads:
    def __init__(self, metrics):
        self.requested = []
        self._metrics = metrics

    def get_insights(self, ids):
        self.requested.extend(ids)
        return {i: self._metrics[i] for i in ids if i in self._metrics}


def test_refresh_routes_ids_to_their_platform():
    rows = [
        _row("111", "X", hours_ago=30),
        _row("222", "Threads", hours_ago=30),
        _row("333", "X", hours_ago=5),          # too fresh — outside window
        _row("DRYRUN-x", "X", hours_ago=48),    # simulated post — never refreshed
    ]
    notion = FakeNotion(rows)
    twitter = FakeTwitter({"111": {"impressions": 100, "likes": 3, "replies": 1, "reposts": 2, "link_clicks": 4}})
    threads = FakeThreads({"222": {"impressions": 50, "likes": 4, "replies": 0, "reposts": 1, "quotes": 0}})

    learn_loop.run(dry_run=False, notion=notion, twitter=twitter, threads=threads)

    assert twitter.requested == ["111"]
    assert threads.requested == ["222"]
    assert notion.updates["page-111"][Performance.IMPRESSIONS] == 100
    assert notion.updates["page-222"][Performance.IMPRESSIONS] == 50
    assert notion.updates["page-222"][Performance.LIKES] == 4
    assert "page-333" not in notion.updates
    assert "page-DRYRUN-x" not in notion.updates


def test_refresh_reads_each_post_exactly_once():
    # Reads spend the same monthly credit budget as writes: only the [24h,48h)
    # window is read — older rows are NEVER re-read, even with no impressions.
    rows = [
        _row("in-window", "X", hours_ago=30),
        _row("too-old", "X", hours_ago=50, impressions=0.0),
        _row("ancient-empty", "X", hours_ago=100, impressions=0.0),
    ]
    notion = FakeNotion(rows)
    twitter = FakeTwitter({"in-window": {"impressions": 80, "likes": 1, "replies": 0, "reposts": 0}})

    learn_loop.run(dry_run=False, notion=notion, twitter=twitter, threads=FakeThreads({}))

    assert twitter.requested == ["in-window"]
    assert notion.updates["page-in-window"][Performance.IMPRESSIONS] == 80


def test_x_write_budget_telemetry_counts_x_rows_this_month():
    rows = [
        _row("x-post", "X", hours_ago=0.5),
        _row("th-post", "Threads", hours_ago=0.5),
        _row("DRYRUN-sim", "X", hours_ago=0.5),
    ]
    summary = learn_loop.run(
        dry_run=False, notion=FakeNotion(rows),
        twitter=FakeTwitter({}), threads=FakeThreads({}),
    )
    assert summary["x_writes_month"] == 1  # real X rows only


def test_refresh_without_threads_service_leaves_threads_rows_alone():
    rows = [_row("222", "Threads", hours_ago=30)]
    notion = FakeNotion(rows)
    twitter = FakeTwitter({})

    summary = learn_loop.run(dry_run=False, notion=notion, twitter=twitter, threads=None)

    assert twitter.requested == []
    assert notion.updates == {}
    assert summary["rows"] == 1


def test_public_only_metrics_do_not_zero_existing_impressions():
    rows = [_row("111", "X", hours_ago=30, impressions=250.0)]
    notion = FakeNotion(rows)
    # Fallback path: metrics dict without impressions/link_clicks keys.
    twitter = FakeTwitter({"111": {"likes": 9, "replies": 2, "reposts": 1}})

    learn_loop.run(dry_run=False, notion=notion, twitter=twitter, threads=FakeThreads({}))

    update = notion.updates["page-111"]
    assert update[Performance.IMPRESSIONS] == 250.0   # preserved
    assert update[Performance.LIKES] == 9
