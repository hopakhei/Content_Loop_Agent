"""Agent Rules read/write paths (the consolidation contract) with a fake client."""
import config.settings as settings
from services.notion import NotionService


def _rule_page(title, content, status="Active", version=1, loop=1):
    return {
        "id": f"pg-{title}",
        "properties": {
            "Rule Title": {"title": [{"plain_text": title}]},
            "Rule Content": {"rich_text": [{"plain_text": content}]},
            "Status": {"select": {"name": status}},
            "Category": {"select": {"name": "Meta"}},
            "Version": {"number": version},
            "Loop": {"number": loop},
        },
    }


def _title_of(page):
    parts = page["properties"]["Rule Title"]["title"]
    return "".join(p.get("plain_text", "") for p in parts)


class FakeDB:
    def __init__(self, rows=None):
        self.rows = rows or []

    def query(self, data_source_id, **kw):
        flt = kw.get("filter") or {}
        if flt.get("property") == "Rule Title":
            wanted = flt["title"]["equals"]
            res = [r for r in self.rows if _title_of(r) == wanted]
        else:
            res = self.rows
        return {"results": res, "has_more": False, "next_cursor": None}


class FakePages:
    def __init__(self):
        self.created = []
        self.updated = []

    def create(self, parent, properties):
        self.created.append(properties)
        return {"id": f"new-{len(self.created)}"}

    def update(self, page_id, properties):
        self.updated.append((page_id, properties))

    def retrieve(self, page_id):
        return {"id": page_id, "properties": {}}


class FakeClient:
    def __init__(self, rows=None):
        self.data_sources = FakeDB(rows)
        self.pages = FakePages()


def _content(props):
    return props["Rule Content"]["rich_text"][0]["text"]["content"]


def test_get_rules_parses_active_operational_rows(monkeypatch):
    monkeypatch.setattr(settings, "NOTION_AGENT_RULES_DB", "db")
    client = FakeClient([
        _rule_page("Daily Limit", "7"),
        _rule_page("Best Hook", "B"),
        _rule_page("Best Slots", '["21:30", "07:30"]'),
        _rule_page("Best Content Types", '["反共識", "Thread"]'),
        _rule_page("LEARN Summary", "Hooks B win at night."),
        _rule_page("反共識 hooks beat 數據衝擊", "narrative", status="Active"),
    ])
    rules = NotionService(client=client).get_rules()
    assert rules.daily_limit == 7
    assert rules.best_hook_type == "B"
    assert rules.best_slots == ["21:30", "07:30"]
    assert rules.best_content_types == ["反共識", "Thread"]
    assert rules.notes == "Hooks B win at night."


def test_get_rules_none_when_db_unset(monkeypatch):
    monkeypatch.setattr(settings, "NOTION_AGENT_RULES_DB", "")
    assert NotionService(client=FakeClient()).get_rules() is None


def test_get_rules_none_when_no_operational_rows(monkeypatch):
    monkeypatch.setattr(settings, "NOTION_AGENT_RULES_DB", "db")
    client = FakeClient([_rule_page("Some narrative insight", "prose")])
    assert NotionService(client=client).get_rules() is None


def test_write_rules_creates_operational_rows(monkeypatch):
    monkeypatch.setattr(settings, "NOTION_AGENT_RULES_DB", "db")
    client = FakeClient([])  # nothing exists yet -> every upsert creates
    ok = NotionService(client=client).write_rules(
        daily_limit=5,
        best_hook="B",
        best_slots=["21:30", "07:30"],
        best_content_types=["反共識"],
        confidence=75,
        evidence_post_ids=["1001", "1002"],
        loop_iteration=3,
        summary="prose",
    )
    assert ok is True
    titles = {p["Rule Title"]["title"][0]["text"]["content"] for p in client.pages.created}
    assert titles == {"Daily Limit", "Best Hook", "Best Slots", "Best Content Types", "LEARN Summary"}
    best_hook_row = next(p for p in client.pages.created
                         if p["Rule Title"]["title"][0]["text"]["content"] == "Best Hook")
    assert _content(best_hook_row) == "B"
    assert best_hook_row["Confidence"]["number"] == 75
    assert best_hook_row["Status"]["select"]["name"] == "Active"


def test_write_rules_noop_when_db_unset(monkeypatch):
    monkeypatch.setattr(settings, "NOTION_AGENT_RULES_DB", "")
    client = FakeClient([])
    ok = NotionService(client=client).write_rules(
        daily_limit=5, best_hook="A", best_slots=[], best_content_types=[],
        confidence=50, evidence_post_ids=[], loop_iteration=1, summary="",
    )
    assert ok is False
    assert client.pages.created == []
