"""Edits to a unit file after insertion have to reach Notion.

Before this script existed they did not, and nothing said so: the insert ledger
skips a slug forever once it is written, so a rewritten hook lived in git while
the old one kept posting. That is the failure mode this repo keeps re-learning —
a green run that changed nothing — so the resync gets tests for the two things
that make it trustworthy: it notices drift, and it refuses to touch history.
"""
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import resync_drafts  # noqa: E402

UNIT = """working notes above the fence

---
【19】【Thread】【X + Threads】
Hook A（反共識）：新鈎 A
Hook B（場景開場）：新鈎 B
Hook C（懸念缺口）：新鈎 C
Post Body：新的內文。
---
第二段。
{CTA_URL}
"""


class FakeDraft:
    def __init__(self, title, hooks, post_body, did="pg-1"):
        self.id = did
        self.title = title
        self.hooks = hooks
        self.post_body = post_body


class FakeNotion:
    def __init__(self, draft=None, scheduled=None):
        self._draft = draft or []
        self._scheduled = scheduled or []
        self.updates = []

    def query_drafts_by_status(self, status):
        return list(self._draft) if status == "Draft" else list(self._scheduled)

    def update_draft_text(self, draft_id, hooks, post_body):
        self.updates.append({"id": draft_id, "hooks": hooks, "post_body": post_body})


@pytest.fixture
def repo(tmp_path, monkeypatch):
    (tmp_path / "units").mkdir()
    (tmp_path / "units" / "profit-formula.md").write_text(UNIT, encoding="utf-8")
    (tmp_path / "state").mkdir()
    (tmp_path / "state" / "inserted_units.txt").write_text("profit-formula\n", encoding="utf-8")
    monkeypatch.setattr(resync_drafts, "UNITS", tmp_path / "units")
    monkeypatch.setattr(resync_drafts, "LEDGER", tmp_path / "state" / "inserted_units.txt")
    return tmp_path


def _install(monkeypatch, notion):
    """`run` imports services.notion lazily so the module stays importable
    without a token; swap the class it will construct."""
    module = types.ModuleType("services.notion")
    module.NotionService = lambda *a, **k: notion
    monkeypatch.setitem(sys.modules, "services.notion", module)


def test_a_rewritten_hook_reaches_notion(repo, monkeypatch):
    notion = FakeNotion(draft=[FakeDraft(
        "#profit-formula-19 Thread",
        {"A": "舊鈎 A", "B": "新鈎 B", "C": "新鈎 C"},
        "新的內文。\n---\n第二段。\n{CTA_URL}",
    )])
    _install(monkeypatch, notion)
    out = resync_drafts.run()
    assert out["updated"] == ["profit-formula"]
    assert notion.updates[0]["hooks"]["A"] == "新鈎 A"


def test_dry_run_writes_nothing(repo, monkeypatch):
    notion = FakeNotion(draft=[FakeDraft(
        "#profit-formula-19 Thread", {"A": "舊鈎 A", "B": "", "C": ""}, "舊內文",
    )])
    _install(monkeypatch, notion)
    out = resync_drafts.run(dry_run=True)
    assert out["updated"] == ["profit-formula"] and notion.updates == []


def test_a_draft_that_already_matches_is_left_alone(repo, monkeypatch):
    hooks = {"A": "新鈎 A", "B": "新鈎 B", "C": "新鈎 C"}
    notion = FakeNotion(draft=[FakeDraft(
        "#profit-formula-19 Thread", hooks, "新的內文。\n---\n第二段。\n{CTA_URL}",
    )])
    _install(monkeypatch, notion)
    out = resync_drafts.run()
    assert out["updated"] == [] and out["in_sync"] == ["profit-formula"]
    assert notion.updates == []


def test_posted_drafts_are_never_rewritten(repo, monkeypatch):
    """Only Draft/Scheduled are queried. A posted row is what the audience read
    and what research/cards.py scores against — rewriting it would move posts
    between experiment arms after the fact."""
    notion = FakeNotion()          # nothing un-posted
    _install(monkeypatch, notion)
    out = resync_drafts.run()
    assert notion.updates == [] and out["no_live_draft"] == ["profit-formula"]


def test_slugs_with_digits_and_hyphens_still_match_their_draft(repo, monkeypatch):
    """`mckinsey-7s-23` splits on the last hyphen, not the first."""
    (repo / "units" / "mckinsey-7s.md").write_text(UNIT, encoding="utf-8")
    (repo / "state" / "inserted_units.txt").write_text("mckinsey-7s\n", encoding="utf-8")
    notion = FakeNotion(draft=[FakeDraft(
        "#mckinsey-7s-23 Thread", {"A": "舊", "B": "舊", "C": "舊"}, "舊內文",
    )])
    _install(monkeypatch, notion)
    assert resync_drafts.run()["updated"] == ["mckinsey-7s"]


def test_a_ledger_entry_with_no_file_is_reported(repo, monkeypatch):
    (repo / "state" / "inserted_units.txt").write_text("gone-framework\n", encoding="utf-8")
    _install(monkeypatch, FakeNotion())
    assert resync_drafts.run()["missing_file"] == ["gone-framework"]
