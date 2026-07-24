"""Preflight verify() paths for Notion and X, with fakes."""
import config.settings as settings
from services.notion import NotionService
from services.twitter import TwitterService


class _DataSources:
    def __init__(self, ok_ids):
        self.ok_ids = ok_ids

    def retrieve(self, data_source_id):
        if data_source_id in self.ok_ids:
            return {"id": data_source_id}
        raise RuntimeError("APIResponseError: object_not_found")


class _NotionClient:
    def __init__(self, ok_ids):
        self.data_sources = _DataSources(ok_ids)


def test_verify_databases_reports_per_db(monkeypatch):
    monkeypatch.setattr(settings, "NOTION_ARTICLE_LIBRARY_DB", "a")
    monkeypatch.setattr(settings, "NOTION_CONTENT_DRAFTS_DB", "b")
    monkeypatch.setattr(settings, "NOTION_PERFORMANCE_LOG_DB", "c")
    monkeypatch.setattr(settings, "NOTION_AGENT_RULES_DB", "d")
    svc = NotionService(client=_NotionClient({"a", "b", "c"}))  # 'd' not shared
    res = {label: ok for label, ok, _ in svc.verify_databases()}
    assert res == {
        "Article Library": True,
        "Content Drafts": True,
        "Post Performance": True,
        "Agent Rules": False,
    }


class _Me:
    class data:
        username = "ninetypm_investing"


class _XClient:
    def get_me(self):
        return _Me()


def test_twitter_verify_returns_handle():
    assert TwitterService(client=_XClient()).verify() == "ninetypm_investing"
