"""Cutting a finished article into posts, without losing any of it.

Everything else this repo publishes is composed — a hook is chosen, an opening
is written, a CTA is appended. A long article dispatched through
`scripts/post_longform.py` is the one case where the text is finished before it
arrives and the only decision left is where to cut it, so the thing worth
testing is that the cuts put nothing at risk: no character dropped, no URL
split in half, no section heading stranded at the bottom of a post.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))
import post_longform as lf  # noqa: E402

ARTICLE = ROOT / "longform" / "2026-09-11-lean-stock-tree.md"


@pytest.fixture(scope="module")
def article() -> str:
    return ARTICLE.read_text("utf-8").strip()


def test_no_threads_post_exceeds_the_limit(article):
    posts = lf.segment(article, lf.THREADS_LIMIT)
    assert posts and max(len(p) for p in posts) <= lf.THREADS_LIMIT


def test_the_chain_is_the_whole_article(article):
    """The instruction was 一字不漏. This is what enforces it: re-join the chain,
    drop the whitespace the cuts themselves moved, and demand the same text."""
    lf.verify_verbatim(article, lf.segment(article, lf.THREADS_LIMIT))


def test_a_dropped_character_is_caught():
    """The check above is only worth having if it can fail."""
    source = "第一句。第二句。第三句。"
    with pytest.raises(ValueError, match="not verbatim"):
        lf.verify_verbatim(source, ["第一句。第二句。"])


def test_a_url_is_never_split(article):
    """Half a URL is a dead link in both posts, and this article carries seven."""
    rx = re.compile(r"https?://[^\s）]+")
    posts = lf.segment(article, lf.THREADS_LIMIT)
    assert [u for p in posts for u in rx.findall(p)] == rx.findall(article)


def test_a_section_heading_opens_its_post(article):
    """A heading that lands at the bottom of a post names a section the reader
    has to tap through to reach. Headings start posts or the cut was wrong."""
    posts = lf.segment(article, lf.THREADS_LIMIT)
    for p in posts:
        lines = [ln for ln in p.splitlines() if ln.strip()]
        heads = [i for i, ln in enumerate(lines) if lf._HEADING.match(ln)]
        assert heads in ([], [0]), f"heading is not at the top of: {lines[:1]}"


def test_the_article_fits_one_x_post(article):
    """X Premium takes 25,000 characters, so an article of this length is one
    post and one write against the monthly quota, not a twenty-tweet chain."""
    assert lf.plan(article, ["X"])["X"] == [article]


def test_an_oversized_paragraph_falls_back_to_sentences_then_commas():
    para = "一" * 90 + "。" + "二" * 90 + "。"
    assert lf._fit(para, 100) == ["一" * 90 + "。", "二" * 90 + "。"]
    # No sentence end to cut on — the commas are what is left.
    comma_only = "甲" * 60 + "，" + "乙" * 60 + "，" + "丙" * 20
    assert all(len(p) <= 100 for p in lf._fit(comma_only, 100))


def test_a_comma_inside_a_url_is_not_a_cut_point():
    """Full-width commas don't appear in URLs, but ASCII ones do, and _commas
    is the last line of defence before a blind cut."""
    s = "見 https://example.com/a，b/c 這一頁，另外還有別的。"
    assert all("https://example.com/a，b/c" in p for p in lf._commas(s)
               if "example.com" in p)


def test_paragraphs_stay_whole_when_they_fit():
    text = "第一段。\n\n第二段。\n\n第三段。"
    assert lf.segment(text, 500) == ["第一段。\n\n第二段。\n\n第三段。"]
    assert lf.segment(text, 8) == ["第一段。", "第二段。", "第三段。"]
