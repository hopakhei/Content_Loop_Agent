"""End-to-end Loop 1 flow with fake Notion/X services (no network)."""
import pytest

from config import settings as _settings
from core.models import Article, Draft
from loops import post_loop
from services.errors import PartialThreadError


@pytest.fixture(autouse=True)
def _deterministic_x_link(monkeypatch):
    """Disable the randomized X link A/B by default so link-presence assertions
    are deterministic; the A/B itself is exercised explicitly below."""
    monkeypatch.setattr(_settings, "X_LINK_AB", False)


class FakeNotion:
    def __init__(self, drafts):
        self._drafts = drafts
        self.marked = []
        self.performance = []
        self.parked_until = None

    def get_rules(self):
        return None

    def get_x_parked_until(self):
        return self.parked_until

    def park_x_until(self, until):
        self.parked_until = until

    def unpark_x(self):
        self.parked_until = None

    def count_posts_today(self, ref):
        return 0, {}

    def list_articles(self):
        return [Article(id="A", cta_url="https://90spm.substack.com/p/102?r=x")]

    def query_drafts_by_status(self, status):
        # Return remaining drafts of that status that haven't been marked posted.
        return [d for d in self._drafts if d.status == status and d.id not in self.marked]

    def get_article(self, article_id):
        return Article(id="A", cta_url="https://90spm.substack.com/p/102?r=x")

    def mark_draft_posted(self, draft_id):
        self.marked.append(draft_id)

    def create_performance_record(self, **kwargs):
        self.performance.append(kwargs)
        return "perf-1"


class FakeTwitter:
    def __init__(self):
        self.threads = []

    def post_thread(self, tweets):
        self.threads.append(tweets)
        return [f"100{i}" for i, _ in enumerate(tweets)]


def _draft():
    return Draft(
        id="d1",
        title="#102-01 反共識",
        post_body="止損不是紀律。",
        hooks={"A": "反共識鈎", "B": "", "C": ""},
        content_type="反共識",
        platforms=["X"],
        status="Draft",
        article_id="A",
        argument_num=1,
    )


def test_loop1_posts_and_records():
    notion = FakeNotion([_draft()])
    twitter = FakeTwitter()
    summary = post_loop.run(dry_run=False, slot="12:30", assume_yes=True, notion=notion, twitter=twitter)

    assert len(summary["posted"]) == 1
    result = summary["posted"][0]
    assert result["post_id"] == "1000"
    assert notion.marked == ["d1"]
    assert len(notion.performance) == 1
    assert notion.performance[0]["platform"] == "X"
    assert notion.performance[0]["loop_version"] == post_loop.COMPOSITION_VERSION
    # X carries the CTA as a bare link (default on) — one tweet, no sell copy.
    assert len(twitter.threads[0]) == 1
    root = twitter.threads[0][0]
    assert root.startswith("反共識鈎")
    assert "👉" not in root and "完整框架" not in root
    assert "https://90spm.substack.com/p/102?r=x" in root


def test_loop1_dry_run_writes_nothing():
    notion = FakeNotion([_draft()])
    twitter = FakeTwitter()
    summary = post_loop.run(dry_run=True, slot="12:30", assume_yes=True, notion=notion, twitter=twitter)

    assert len(summary["posted"]) == 1
    assert notion.marked == []
    assert notion.performance == []


class FakeThreads:
    def __init__(self):
        self.threads = []

    def post_thread(self, posts):
        self.threads.append(posts)
        return [f"200{i}" for i, _ in enumerate(posts)]


def _dual_draft():
    d = _draft()
    d.platforms = ["X", "Threads"]
    return d


def _threads_only_draft():
    d = _draft()
    d.id = "d2"
    d.title = "#101-09 故事貼"
    d.platforms = ["Threads"]
    return d


def test_loop1_posts_to_both_platforms():
    notion = FakeNotion([_dual_draft()])
    twitter, threads = FakeTwitter(), FakeThreads()
    summary = post_loop.run(
        dry_run=False, slot="12:30", assume_yes=True,
        notion=notion, twitter=twitter, threads=threads,
    )
    result = summary["posted"][0]
    assert sorted(result["platforms"]) == ["Threads", "X"]
    assert len(twitter.threads) == 1 and len(threads.threads) == 1
    # One posting event, one draft marked, but a Performance row per platform.
    assert notion.marked == ["d1"]
    assert sorted(r["platform"] for r in notion.performance) == ["Threads", "X"]
    # Both platforms carry the bare-link CTA — no 👉 sell copy on either.
    link = "https://90spm.substack.com/p/102?r=x"
    assert len(twitter.threads[0]) == 1 and link in twitter.threads[0][0]
    assert "👉" not in twitter.threads[0][0]
    assert len(threads.threads[0]) == 1 and link in threads.threads[0][0]
    assert "👉" not in threads.threads[0][0]


def test_loop1_threads_only_draft_posts_when_threads_configured():
    notion = FakeNotion([_threads_only_draft()])
    twitter, threads = FakeTwitter(), FakeThreads()
    summary = post_loop.run(
        dry_run=False, slot="12:30", assume_yes=True,
        notion=notion, twitter=twitter, threads=threads,
    )
    result = summary["posted"][0]
    assert result["platforms"] == ["Threads"]
    assert twitter.threads == []          # X untouched
    assert len(threads.threads) == 1
    assert notion.performance[0]["platform"] == "Threads"


def test_loop1_x_link_ab_no_link_arm_strips_and_tags(monkeypatch):
    monkeypatch.setattr(_settings, "X_LINK_AB", True)
    monkeypatch.setattr(post_loop.random, "random", lambda: 0.1)  # < 0.5 → no_link
    notion = FakeNotion([_dual_draft()])
    twitter, threads = FakeTwitter(), FakeThreads()
    post_loop.run(dry_run=False, slot="12:30", assume_yes=True,
                  notion=notion, twitter=twitter, threads=threads)
    x_post = twitter.threads[0][0]
    assert "substack" not in x_post                      # link stripped
    xrow = next(r for r in notion.performance if r["platform"] == "X")
    assert xrow["tags"]["x_link_arm"] == "no_link"
    assert xrow["tags"]["has_link"] is False
    # Threads is never in the A/B — keeps its link.
    assert "substack" in threads.threads[0][0]


def test_loop1_x_link_ab_link_arm_keeps_and_tags(monkeypatch):
    monkeypatch.setattr(_settings, "X_LINK_AB", True)
    monkeypatch.setattr(post_loop.random, "random", lambda: 0.9)  # >= 0.5 → link
    notion = FakeNotion([_dual_draft()])
    twitter = FakeTwitter()
    post_loop.run(dry_run=False, slot="12:30", assume_yes=True, notion=notion, twitter=twitter)
    xrow = next(r for r in notion.performance if r["platform"] == "X")
    assert xrow["tags"]["x_link_arm"] == "link"
    assert xrow["tags"]["has_link"] is True
    assert "substack" in twitter.threads[0][0]


class ExplodingThreads:
    def post_thread(self, posts):
        raise RuntimeError("Threads publish failed: 400 Media ID is not available")


def test_loop1_platform_failure_lands_in_summary_failures():
    notion = FakeNotion([_dual_draft()])
    summary = post_loop.run(
        dry_run=False, slot="12:30", assume_yes=True,
        notion=notion, twitter=FakeTwitter(), threads=ExplodingThreads(),
    )
    # X still posted and was recorded; the Threads failure is surfaced so
    # main.py exits non-zero and the workflow files the failure notice.
    assert summary["posted"][0]["platforms"] == ["X"]
    assert len(summary["failures"]) == 1
    assert summary["failures"][0]["platform"] == "Threads"
    assert "Media ID" in summary["failures"][0]["error"]


def _three_hook_draft():
    d = _draft()
    d.hooks = {"A": "鈎A開場", "B": "鈎B開場", "C": "鈎C開場"}
    d.platforms = ["X", "Threads"]
    return d


def test_loop1_dual_platform_uses_different_hooks():
    notion = FakeNotion([_three_hook_draft()])
    twitter, threads = FakeTwitter(), FakeThreads()
    summary = post_loop.run(
        dry_run=False, slot="12:30", assume_yes=True,
        notion=notion, twitter=twitter, threads=threads,
    )
    x_open = twitter.threads[0][0].splitlines()[0]
    th_open = threads.threads[0][0].splitlines()[0]
    assert x_open != th_open                      # cross-platform hook A/B
    hooks_used = summary["posted"][0]["hooks_used"]
    assert hooks_used["X"] != hooks_used["Threads"]
    # Each Performance row records its own platform's hook.
    labels = {r["platform"]: r["hook_label"] for r in notion.performance}
    assert labels["X"] != labels["Threads"]


def _bip_draft():
    # Build-in-public series (2xx): X carries the GitHub repo instead of the
    # Substack CTA (X_CTA_BY_ISSUE default mapping for issue 201).
    d = _draft()
    d.title = "#201-04 數據衝擊"
    d.post_body = "主體內容。\n\n{CTA_URL}"
    d.platforms = ["X", "Threads"]
    return d


def test_loop1_x_uses_github_cta_for_build_in_public_issue():
    notion = FakeNotion([_bip_draft()])
    twitter, threads = FakeTwitter(), FakeThreads()
    post_loop.run(
        dry_run=False, slot="12:30", assume_yes=True,
        notion=notion, twitter=twitter, threads=threads,
    )
    x_post = twitter.threads[0][0]
    th_post = threads.threads[0][0]
    assert "github.com/Draw-Tree/tree-quant-ledger" in x_post
    assert "substack" not in x_post
    assert "https://90spm.substack.com/p/102?r=x" in th_post
    assert "github.com" not in th_post


def _thread_draft():
    return Draft(
        id="d3",
        title="#107-01 框架拆解",
        post_body="鈎子推文\n---\n第二條\n---\n第三條",
        hooks={"A": "", "B": "", "C": ""},
        content_type="Thread",
        platforms=["X", "Threads"],
        status="Draft",
        article_id="A",
        argument_num=1,
    )


def test_loop1_caps_x_thread_at_root_but_threads_gets_full_chain():
    notion = FakeNotion([_thread_draft()])
    twitter, threads = FakeTwitter(), FakeThreads()
    post_loop.run(
        dry_run=False, slot="12:30", assume_yes=True,
        notion=notion, twitter=twitter, threads=threads,
    )
    # X: root tweet only (each chained tweet costs a monthly write credit).
    assert len(twitter.threads[0]) == 1
    assert twitter.threads[0][0].startswith("鈎子推文")
    # Threads: full chain + its CTA tweet (a bare link; Threads API is free).
    assert len(threads.threads[0]) == 4
    assert threads.threads[0][-1] == "https://90spm.substack.com/p/102?r=x"


class QuotaExhaustedTwitter:
    def post_thread(self, tweets):
        raise RuntimeError(
            "402 Payment Required\nYour enrolled account does not have any credits to fulfill this request."
        )


def test_loop1_402_parks_x_until_next_month():
    notion = FakeNotion([_dual_draft()])
    summary = post_loop.run(
        dry_run=False, slot="12:30", assume_yes=True,
        notion=notion, twitter=QuotaExhaustedTwitter(), threads=FakeThreads(),
    )
    assert notion.parked_until is not None and notion.parked_until.day == 1
    assert summary["posted"][0]["platforms"] == ["Threads"]  # Threads unaffected
    assert summary["failures"][0]["platform"] == "X"


def test_loop1_parked_x_posts_threads_only_without_failures():
    from datetime import date, timedelta

    notion = FakeNotion([_dual_draft()])
    notion.parked_until = date.today() + timedelta(days=5)
    twitter, threads = FakeTwitter(), FakeThreads()
    summary = post_loop.run(
        dry_run=False, slot="12:30", assume_yes=True,
        notion=notion, twitter=twitter, threads=threads,
    )
    assert twitter.threads == []                      # X never attempted
    assert summary["posted"][0]["platforms"] == ["Threads"]
    assert summary["failures"] == []                  # parked ≠ failing


def test_loop1_expired_park_resumes_x():
    from datetime import date, timedelta

    notion = FakeNotion([_dual_draft()])
    notion.parked_until = date.today() - timedelta(days=40)
    twitter, threads = FakeTwitter(), FakeThreads()
    summary = post_loop.run(
        dry_run=False, slot="12:30", assume_yes=True,
        notion=notion, twitter=twitter, threads=threads,
    )
    assert notion.parked_until is None                # rule deprecated
    assert sorted(summary["posted"][0]["platforms"]) == ["Threads", "X"]


class PartialTwitter:
    """Posts the root tweet then dies — like hitting the write cap mid-thread."""

    def post_thread(self, tweets):
        raise PartialThreadError(["7770"], RuntimeError("403 Forbidden"))


def test_loop1_partial_thread_records_root_instead_of_retrying():
    notion = FakeNotion([_draft()])
    summary = post_loop.run(
        dry_run=False, slot="12:30", assume_yes=True,
        notion=notion, twitter=PartialTwitter(),
    )
    # The live root tweet is recorded so the next slot won't duplicate it.
    result = summary["posted"][0]
    assert result["post_id"] == "7770"
    assert notion.marked == ["d1"]
    assert notion.performance[0]["post_id"] == "7770"
