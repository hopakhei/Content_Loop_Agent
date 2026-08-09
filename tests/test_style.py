"""Shape and the de-AI list, enforced instead of remembered.

Two complaints arrived together, and they had the same cause. The batch had
drifted to nine segments — nine subjects, no spine, which reads as a list even
when every line is true. And the corpus held 33 uses of 東西 and 19 of 這件事
against a single 其實: the de-AI pass had been catching the memorable half of
the renhua ban list and missing the common half, because nothing checked it.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import audit_style as ast_  # noqa: E402


def test_everything_still_publishable_is_clean():
    rows = [ast_.audit(s) for s in ast_.framework_slugs()]
    posted = ast_.posted_slugs()
    bad = {r["slug"]: ast_.problems(r) for r in rows
           if r["slug"] not in posted and not r["ok"]}
    assert not bad, f"unpublished units breaking shape or the ban list: {bad}"


def test_the_posted_ledger_is_not_empty():
    """Every check that grandfathers published content depends on this file.
    Empty means either a first run or a bad Notion read, and in the second case
    the style check silently starts demanding edits to posts already read."""
    assert len(ast_.posted_slugs()) >= 20


def test_nine_segments_fails_and_five_passes():
    body = "\n---\n".join(["起" * 150] * 9)
    assert ast_.segments(body).__len__() == 9
    assert len(ast_.segments("\n---\n".join(["起" * 150] * 5))) == 5


def test_the_vague_referent_bans_are_covered():
    """These two were the whole gap: they are the most common bans in the list
    and the ones no pass ever caught."""
    labels = [label for label, _ in ast_.BANS]
    assert any("東西" in x for x in labels)
    assert any("這件事" in x for x in labels)


def test_a_binary_contrast_shell_is_caught():
    rx = dict((label, rx) for label, rx in ast_.BANS)["二元對比殼「不是…而是」"]
    assert rx.search("去 AI 味不是把文章改口語，而是保住判斷")
    # A 不是 and a 而是 in different sentences are two ordinary words.
    assert not rx.search("這不是重點。他而是走了另一條路")


def test_a_short_segment_is_a_bullet_not_a_paragraph():
    assert ast_.MIN_SEGMENT_CHARS >= 100
    assert ast_.MAX_SEGMENTS == 5
