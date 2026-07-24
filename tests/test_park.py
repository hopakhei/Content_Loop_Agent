"""Loop 3 fresh-start: park_drafts moves an article's unposted drafts to Optimizing."""
import config.settings as settings
from services.notion import NotionService


def _draft_page(pid, source, status):
    return {"id": pid, "properties": {
        "Status": {"select": {"name": status}},
        "Source Article": {"select": {"name": source}},
    }}


class _DS:
    def __init__(self, drafts):
        self.drafts = drafts

    def query(self, data_source_id, **kw):
        want = (kw.get("filter") or {}).get("select", {}).get("equals")
        res = [d for d in self.drafts if d["properties"]["Status"]["select"]["name"] == want]
        return {"results": res, "has_more": False, "next_cursor": None}


class _Pages:
    def __init__(self):
        self.updated = []

    def update(self, page_id, properties):
        self.updated.append((page_id, properties))


class _Client:
    def __init__(self, drafts):
        self.data_sources = _DS(drafts)
        self.pages = _Pages()


def test_park_drafts_matches_source_article(monkeypatch):
    monkeypatch.setattr(settings, "NOTION_CONTENT_DRAFTS_DB", "x")
    drafts = [
        _draft_page("p102", "102 - 北極星", "Draft"),
        _draft_page("p105", "105 - 畫樹", "Draft"),
        _draft_page("p102b", "102 - 北極星", "Posted"),  # posted → not parked
    ]
    svc = NotionService(client=_Client(drafts))

    parked = svc.park_drafts(source_article="102 - 北極星")

    assert parked == 1
    assert [pid for pid, _ in svc.client.pages.updated] == ["p102"]
    assert svc.client.pages.updated[0][1]["Status"]["select"]["name"] == "Optimizing"


def test_park_drafts_noop_without_target():
    svc = NotionService(client=_Client([]))
    assert svc.park_drafts() == 0
