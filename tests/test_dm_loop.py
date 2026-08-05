"""Comment-to-DM loop: keyword matching, self-skip, idempotent state, caps."""
from datetime import datetime, timedelta, timezone

import pytest

from config import settings as _settings
from loops import dm_loop

NOW = datetime(2026, 7, 17, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _isolate_comment_log(tmp_path, monkeypatch):
    """Keep fixture comments out of research/audience/ig_comments.jsonl.

    That file is meant to hold what real readers wrote; a test that appends to
    it is manufacturing the evidence the research loop later reads back."""
    monkeypatch.setattr(dm_loop, "COMMENT_LOG", str(tmp_path / "ig_comments.jsonl"))


def _iso(hours_ago=1.0):
    return (NOW - timedelta(hours=hours_ago)).strftime("%Y-%m-%dT%H:%M:%S+0000")


class FakeIG:
    def __init__(self, media=None, comments=None):
        self._media = media or [{"id": "M1", "timestamp": _iso(24)}]
        self._comments = comments or {}
        self.replies = []

    def verify(self):
        return "ninetypm_ig"

    def get_recent_media(self, limit=25):
        return list(self._media)

    def get_comments(self, media_id, limit=50):
        return list(self._comments.get(media_id, []))

    def send_private_reply(self, comment_id, text):
        self.replies.append((comment_id, text))
        return "mid-1"


class FakeNotion:
    def __init__(self, rows=None):
        self._rows = rows or []

    def get_performance_rows(self, since_days=30):
        return self._rows


def _comment(cid, text, username="fan1", hours_ago=1.0):
    return {"id": cid, "text": text, "username": username, "timestamp": _iso(hours_ago)}


def test_keyword_comment_gets_dm_with_media_link(tmp_path):
    state = str(tmp_path / "state.json")
    ig = FakeIG(comments={"M1": [
        _comment("c1", "全文 唔該！"),
        _comment("c2", "好正"),                          # no keyword — no DM
        _comment("c3", "全文", username="ninetypm_ig"),   # our own comment
    ]})
    notion = FakeNotion([{"post_id": "M1", "platform": "Instagram",
                          "tags": {"cta": "https://sub/p/101?r=x"}}])

    summary = dm_loop.run(dry_run=False, ig=ig, notion=notion, state_file=state, now=NOW)

    assert summary["sent"] == 1
    assert ig.replies == [("c1", _settings.IG_DM_TEXT.format(url="https://sub/p/101?r=x"))]
    # All three comments are now handled — the next run touches none of them.
    ig2 = FakeIG(comments={"M1": [_comment("c1", "全文 唔該！")]})
    summary2 = dm_loop.run(dry_run=False, ig=ig2, notion=notion, state_file=state, now=NOW)
    assert summary2["sent"] == 0 and ig2.replies == []


def test_falls_back_to_default_url_without_cta_tag(tmp_path):
    ig = FakeIG(comments={"M1": [_comment("c1", "全文")]})
    dm_loop.run(dry_run=False, ig=ig, notion=FakeNotion([]),
                state_file=str(tmp_path / "s.json"), now=NOW)
    assert _settings.IG_DM_FALLBACK_URL in ig.replies[0][1]


def test_dry_run_sends_nothing_and_keeps_no_state(tmp_path):
    state = str(tmp_path / "s.json")
    ig = FakeIG(comments={"M1": [_comment("c1", "全文")]})
    dm_loop.run(dry_run=True, ig=ig, notion=FakeNotion([]), state_file=state, now=NOW)
    assert ig.replies == []
    # Nothing persisted — a later real run still DMs c1.
    ig2 = FakeIG(comments={"M1": [_comment("c1", "全文")]})
    summary = dm_loop.run(dry_run=False, ig=ig2, notion=FakeNotion([]), state_file=state, now=NOW)
    assert summary["sent"] == 1


def test_comment_past_reply_window_is_skipped(tmp_path):
    ig = FakeIG(comments={"M1": [_comment("c1", "全文", hours_ago=7 * 24)]})
    summary = dm_loop.run(dry_run=False, ig=ig, notion=FakeNotion([]),
                          state_file=str(tmp_path / "s.json"), now=NOW)
    assert summary["sent"] == 0 and ig.replies == []


def test_per_run_cap(monkeypatch, tmp_path):
    monkeypatch.setattr(_settings, "IG_DM_MAX_PER_RUN", 2)
    ig = FakeIG(comments={"M1": [_comment(f"c{i}", "全文", username=f"fan{i}")
                                 for i in range(5)]})
    summary = dm_loop.run(dry_run=False, ig=ig, notion=FakeNotion([]),
                          state_file=str(tmp_path / "s.json"), now=NOW)
    assert summary["sent"] == 2


def test_dm_all_mode_ignores_keyword(monkeypatch, tmp_path):
    monkeypatch.setattr(_settings, "IG_DM_ALL", True)
    ig = FakeIG(comments={"M1": [_comment("c1", "好正 學到嘢")]})
    summary = dm_loop.run(dry_run=False, ig=ig, notion=FakeNotion([]),
                          state_file=str(tmp_path / "s.json"), now=NOW)
    assert summary["sent"] == 1
