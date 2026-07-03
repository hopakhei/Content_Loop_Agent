from loops.generate_loop import discover_articles


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
