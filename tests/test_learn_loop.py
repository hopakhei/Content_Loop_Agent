"""Loop 2 metric refresh: platform routing + refresh window, with fake services."""
from datetime import datetime, timedelta, timezone

from config import settings
from config.schema import Performance
from loops import learn_loop


def _iso(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


def _row(pid, platform, hours_ago, impressions=0.0, hook="A", tags=None, **metrics):
    row = {
        "page_id": f"page-{pid}",
        "post_id": pid,
        "draft_id": "d1",
        "posted_at": _iso(hours_ago),
        "platform": platform,
        "hook_used": f"{hook} - x",
        "content_type": "反共識",
        "impressions": impressions,
        "likes": 0.0,
        "replies": 0.0,
        "reposts": 0.0,
        "link_clicks": 0.0,
        "tags": {"platform": platform, "hook": hook, **(tags or {})},
    }
    row.update(metrics)
    return row


def _aged_row(pid, platform, days_ago, impressions=200.0, hook="A", tags=None, **metrics):
    # Older than the refresh window so it counts as an analysis point without
    # triggering a metrics read.
    return _row(pid, platform, hours_ago=days_ago * 24, impressions=impressions,
                hook=hook, tags=tags, **metrics)


class FakeNotion:
    def __init__(self, rows):
        self._rows = rows
        self.updates = {}
        self.tag_merges = {}
        self.rules_written = None
        self.followers = {}

    def get_performance_rows(self, since_days=30):
        return self._rows

    def update_performance_metrics(self, page_id, metrics, tags_merge=None):
        self.updates[page_id] = metrics
        if tags_merge:
            self.tag_merges[page_id] = tags_merge

    def get_next_loop_iteration(self):
        return 1

    def write_rules(self, **kwargs):
        self.rules_written = kwargs
        return True

    def read_follower_history(self, platform):
        return dict(self.followers.get(platform, {}))

    def write_follower_history(self, platform, history, loop_iteration=0):
        self.followers[platform] = dict(history)


class FakeTwitter:
    def __init__(self, metrics, followers=None):
        self.requested = []
        self._metrics = metrics
        self._followers = followers

    def get_metrics(self, ids):
        self.requested.extend(ids)
        return {i: self._metrics[i] for i in ids if i in self._metrics}

    def get_follower_count(self):
        return self._followers


class FakeThreads:
    def __init__(self, metrics, followers=None):
        self.requested = []
        self._metrics = metrics
        self._followers = followers

    def get_insights(self, ids):
        self.requested.extend(ids)
        return {i: self._metrics[i] for i in ids if i in self._metrics}

    def get_follower_count(self):
        return self._followers


class FakeInstagram:
    def __init__(self, metrics=None, followers=None):
        self.requested = []
        self._metrics = metrics or {}
        self._followers = followers

    def get_insights(self, ids):
        self.requested.extend(ids)
        return {i: self._metrics[i] for i in ids if i in self._metrics}

    def get_follower_count(self):
        return self._followers


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


def test_per_platform_best_hook_uses_growth_on_x_engagement_on_threads():
    rows = []
    # X hook A: profile clicks (growth) but zero engagement.
    rows += [_aged_row(f"xa{i}", "X", 3, hook="A", tags={"profile_clicks": 50}) for i in range(10)]
    # X hook B: high engagement but zero growth signals.
    rows += [_aged_row(f"xb{i}", "X", 3, hook="B", likes=100.0) for i in range(10)]
    # Threads hook C: high engagement.
    rows += [_aged_row(f"tc{i}", "Threads", 3, hook="C", replies=20.0) for i in range(10)]
    notion = FakeNotion(rows)

    summary = learn_loop.run(dry_run=False, notion=notion,
                             twitter=FakeTwitter({}), threads=FakeThreads({}))

    bhp = summary["best_hook_by_platform"]
    assert bhp["X"] == "A"          # growth (profile clicks), not engagement
    assert bhp["Threads"] == "C"
    assert notion.rules_written["best_hook_by_platform"] == bhp


def test_min_cell_n_blocks_a_thin_platform_winner():
    rows = [_aged_row(f"t{i}", "Threads", 3, hook="C", replies=10.0) for i in range(20)]
    rows += [_aged_row(f"x{i}", "X", 3, hook="A", tags={"profile_clicks": 40}) for i in range(3)]
    notion = FakeNotion(rows)

    summary = learn_loop.run(dry_run=False, notion=notion,
                             twitter=FakeTwitter({}), threads=FakeThreads({}))

    assert "Threads" in summary["best_hook_by_platform"]
    assert "X" not in summary["best_hook_by_platform"]   # only 3 X points (< 8)


def test_follower_snapshot_records_and_reports_delta():
    # learn_loop stamps snapshots with the HKT calendar day, so the test must
    # use the same clock or it fails in the 16:00–24:00 UTC window.
    from datetime import date
    from core.timeutil import now as hkt_now
    hkt_today = hkt_now(settings.TZ_NAME).date()
    baseline_day = date.fromordinal(hkt_today.toordinal() - 7).isoformat()
    notion = FakeNotion([_aged_row("x1", "X", 3)])
    notion.followers["X"] = {baseline_day: 950}
    twitter = FakeTwitter({}, followers=1000)

    summary = learn_loop.run(dry_run=False, notion=notion, twitter=twitter, threads=FakeThreads({}))

    assert summary["follower_deltas"]["X"] == 50
    assert notion.followers["X"][hkt_today.isoformat()] == 1000


def test_growth_signals_merged_into_tags_on_refresh():
    notion = FakeNotion([_row("111", "X", hours_ago=30, impressions=300.0)])
    twitter = FakeTwitter({"111": {"impressions": 300, "likes": 2, "replies": 1,
                                   "reposts": 0, "bookmarks": 5, "profile_clicks": 8}})

    learn_loop.run(dry_run=False, notion=notion, twitter=twitter, threads=FakeThreads({}))

    merged = notion.tag_merges["page-111"]
    assert merged["bookmarks"] == 5 and merged["profile_clicks"] == 8
    assert "impressions" not in merged   # numbers go to columns, not tags


def test_follower_delta_helper():
    from datetime import date
    from core.timeutil import now as hkt_now
    ord_today = hkt_now(settings.TZ_NAME).date().toordinal()
    hist = {date.fromordinal(ord_today - 10).isoformat(): 900,
            date.fromordinal(ord_today - 6).isoformat(): 980}
    # 7d baseline = the ≤7-days-ago entry (the -10 one); current 1000 → +100.
    assert learn_loop._follower_delta(hist, 1000, days=7) == 100
    assert learn_loop._follower_delta({}, 1000) is None


def test_refresh_routes_instagram_ids_to_instagram():
    rows = [
        _row("111", "X", hours_ago=30),
        _row("IG9", "Instagram", hours_ago=30),
    ]
    notion = FakeNotion(rows)
    twitter = FakeTwitter({"111": {"impressions": 100, "likes": 3, "replies": 1, "reposts": 2}})
    instagram = FakeInstagram({"IG9": {"impressions": 700, "likes": 40, "replies": 6,
                                       "reposts": 3, "bookmarks": 12, "profile_clicks": 25}})

    learn_loop.run(dry_run=False, notion=notion, twitter=twitter,
                   threads=FakeThreads({}), instagram=instagram)

    assert instagram.requested == ["IG9"]
    assert notion.updates["page-IG9"][Performance.IMPRESSIONS] == 700
    assert notion.updates["page-IG9"][Performance.LIKES] == 40
    # IG growth signals (saved/profile_visits) merge into the row's tags.
    assert notion.tag_merges["page-IG9"] == {"bookmarks": 12, "profile_clicks": 25}


def test_instagram_rows_skipped_without_instagram_service():
    rows = [_row("IG9", "Instagram", hours_ago=30)]
    notion = FakeNotion(rows)

    summary = learn_loop.run(dry_run=False, notion=notion, twitter=FakeTwitter({}),
                             threads=FakeThreads({}), instagram=None)

    assert notion.updates == {}
    assert summary["rows"] == 1


def test_instagram_hook_ranked_and_written():
    rows = [_aged_row(f"ig{i}", "Instagram", 3, hook="B", likes=30.0) for i in range(10)]
    rows += [_aged_row(f"th{i}", "Threads", 3, hook="C", replies=20.0) for i in range(10)]
    notion = FakeNotion(rows)

    summary = learn_loop.run(dry_run=False, notion=notion, twitter=FakeTwitter({}),
                             threads=FakeThreads({}), instagram=FakeInstagram())

    assert summary["best_hook_by_platform"]["Instagram"] == "B"
    assert notion.rules_written["best_hook_by_platform"]["Instagram"] == "B"


def test_instagram_follower_snapshot_recorded():
    notion = FakeNotion([_aged_row("ig1", "Instagram", 3)])
    instagram = FakeInstagram(followers=500)

    summary = learn_loop.run(dry_run=False, notion=notion, twitter=FakeTwitter({}),
                             threads=FakeThreads({}), instagram=instagram)

    from core.timeutil import now as hkt_now
    today = hkt_now(settings.TZ_NAME).date().isoformat()
    assert notion.followers["Instagram"][today] == 500
    assert "Instagram" in summary["follower_deltas"]


def test_public_only_metrics_do_not_zero_existing_impressions():
    rows = [_row("111", "X", hours_ago=30, impressions=250.0)]
    notion = FakeNotion(rows)
    # Fallback path: metrics dict without impressions/link_clicks keys.
    twitter = FakeTwitter({"111": {"likes": 9, "replies": 2, "reposts": 1}})

    learn_loop.run(dry_run=False, notion=notion, twitter=twitter, threads=FakeThreads({}))

    update = notion.updates["page-111"]
    assert update[Performance.IMPRESSIONS] == 250.0   # preserved
    assert update[Performance.LIKES] == 9
