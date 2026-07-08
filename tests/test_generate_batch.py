import pytest

from loops import generate_loop
from loops.generate_loop import discover_articles

UNITS = """---
【1】【框架拆解 Thread】【X + Threads】
Hook A（Statement）：鈎A
Hook B（Question）：鈎B？
Hook C（Narrative）：鈎C
Post Body：第一條
---
第二條
---
完整框架＋案例在 Substack 👉 {CTA_URL}
---
【2】【反共識短貼 A】【Threads / X】
Hook A（Statement）：反A
Hook B（Question）：反B？
Hook C（Conditional）：反C
Post Body：內容。
完整框架＋案例在 Substack 👉 {CTA_URL}
---
"""


class FakeNotion:
    def __init__(self):
        self.created = []

    def list_articles(self):
        return []

    def get_article(self, article_id):
        return None

    def create_draft(self, **kwargs):
        self.created.append(kwargs)
        return f"draft-{len(self.created)}"


def test_units_file_path_inserts_without_claude_api():
    # No `claude` passed and no ANTHROPIC_API_KEY in the test env: this only
    # passes if the units path never constructs ClaudeService.
    notion = FakeNotion()
    summary = generate_loop.run(issue_number=108, units_text=UNITS, notion=notion, cta_url="https://x.example")
    assert summary["created"] == 2
    assert notion.created[0]["title"] == "#108-01 Thread"
    assert notion.created[1]["content_type"] == "反共識"


def test_run_requires_article_or_units():
    with pytest.raises(ValueError):
        generate_loop.run(issue_number=108, notion=FakeNotion())


def test_discover_articles_filters_and_sorts(tmp_path):
    (tmp_path / "102.md").write_text("x", encoding="utf-8")
    (tmp_path / "101.txt").write_text("x", encoding="utf-8")
    (tmp_path / "107.md").write_text("x", encoding="utf-8")
    (tmp_path / "README.md").write_text("x", encoding="utf-8")   # non-digit stem → ignored
    (tmp_path / "draft.doc").write_text("x", encoding="utf-8")   # wrong suffix → ignored

    got = discover_articles(str(tmp_path))
    assert [issue for issue, _ in got] == [101, 102, 107]


def test_discover_articles_empty(tmp_path):
    assert discover_articles(str(tmp_path)) == []
