"""End-to-end Loop 1 flow with fake Notion/X services (no network)."""
from core.models import Article, Draft
from loops import post_loop


class FakeNotion:
    def __init__(self, drafts):
        self._drafts = drafts
        self.marked = []
        self.performance = []

    def get_posting_rules(self):
        return None

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
    # CTA appended to the single post, hook prepended.
    posted_text = twitter.threads[0][0]
    assert posted_text.startswith("反共識鈎")
    assert "👉" in posted_text


def test_loop1_dry_run_writes_nothing():
    notion = FakeNotion([_draft()])
    twitter = FakeTwitter()
    summary = post_loop.run(dry_run=True, slot="12:30", assume_yes=True, notion=notion, twitter=twitter)

    assert len(summary["posted"]) == 1
    assert notion.marked == []
    assert notion.performance == []
