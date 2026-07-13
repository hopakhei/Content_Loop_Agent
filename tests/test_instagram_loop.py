"""Instagram loop: candidate selection, card render, caption + Performance row."""
import pytest

from config import settings as _settings
from core.models import Draft, Rules
from loops import instagram_loop


class FakeNotion:
    def __init__(self, drafts, posted=None):
        self._drafts = drafts
        self._posted = set(posted or ())
        self.performance = []

    def quote_card_drafts(self):
        return list(self._drafts)

    def instagram_posted_draft_ids(self, since_days=90):
        return set(self._posted)

    def get_rules(self):
        return Rules()

    def create_performance_record(self, **kwargs):
        self.performance.append(kwargs)
        return "perf-ig-1"


class FakeIG:
    def __init__(self):
        self.published = []

    def publish_image(self, image_url, caption):
        self.published.append((image_url, caption))
        return "IG-900"


def _card_draft(id="d1", title="#201-06 誠實", body="我哋公開每一步。\n止蝕唔係紀律。\n\n👉 完整框架\n{CTA_URL}"):
    return Draft(
        id=id,
        title=title,
        post_body=body,
        hooks={"A": "我犯過呢個錯", "B": "", "C": ""},
        content_type="Quote Card",
        platforms=["Instagram"],
        status="Draft",
        argument_num=6,
    )


def test_ig_loop_publishes_and_records(monkeypatch, tmp_path):
    monkeypatch.setattr(_settings, "IG_CARD_URL_BASE", "https://raw.githubusercontent.com/o/r/br/")
    notion, ig = FakeNotion([_card_draft()]), FakeIG()
    summary = instagram_loop.run(
        dry_run=False, notion=notion, ig=ig, cards_dir=str(tmp_path / "cards")
    )

    assert summary["posted"] == "IG-900"
    assert (tmp_path / "cards" / "201-06.png").exists()
    image_url, caption = ig.published[0]
    assert image_url == "https://raw.githubusercontent.com/o/r/br/" + str(tmp_path / "cards") + "/201-06.png"
    # Card text drops the CTA/link lines; caption carries hook + bio CTA + tags.
    assert "止蝕唔係紀律" in caption
    assert "{CTA_URL}" not in caption and "👉" not in caption
    assert _settings.IG_CTA_LINE in caption
    assert _settings.IG_HASHTAGS in caption
    row = notion.performance[0]
    assert row["platform"] == "Instagram"
    assert row["post_id"] == "IG-900"
    assert row["tags"]["platform"] == "Instagram"


def test_ig_loop_dry_run_renders_without_publishing(tmp_path):
    notion, ig = FakeNotion([_card_draft()]), FakeIG()
    summary = instagram_loop.run(
        dry_run=True, notion=notion, ig=ig, cards_dir=str(tmp_path / "cards")
    )
    assert summary.get("dry_run") is True
    assert (tmp_path / "cards" / "201-06.png").exists()
    assert ig.published == []
    assert notion.performance == []


def test_ig_loop_skips_already_posted(tmp_path):
    drafts = [_card_draft(id="d1", title="#201-04 A"), _card_draft(id="d2", title="#201-06 B")]
    notion, ig = FakeNotion(drafts, posted={"d1", "d2"}), FakeIG()
    summary = instagram_loop.run(
        dry_run=True, notion=notion, ig=ig, cards_dir=str(tmp_path / "cards")
    )
    assert summary["skipped"] == "no-candidate"
    assert ig.published == []


def test_ig_loop_picks_lowest_argument_num_first(monkeypatch, tmp_path):
    monkeypatch.setattr(_settings, "IG_CARD_URL_BASE", "https://x/")
    d_late = _card_draft(id="d2", title="#201-09 late")
    d_late.argument_num = 9
    d_early = _card_draft(id="d1", title="#201-02 early")
    d_early.argument_num = 2
    notion, ig = FakeNotion([d_late, d_early]), FakeIG()
    instagram_loop.run(dry_run=False, notion=notion, ig=ig, cards_dir=str(tmp_path / "cards"))
    assert notion.performance[0]["draft_id"] == "d1"


def test_ig_loop_real_publish_needs_url_base(monkeypatch, tmp_path):
    monkeypatch.setattr(_settings, "IG_CARD_URL_BASE", "")
    notion, ig = FakeNotion([_card_draft()]), FakeIG()
    summary = instagram_loop.run(
        dry_run=False, notion=notion, ig=ig, cards_dir=str(tmp_path / "cards")
    )
    assert summary["skipped"] == "no-url-base"
    assert ig.published == []
