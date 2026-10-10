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
    assert lf.plan(article, ["X"])["X"] == [lf.Post(article)]


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


def test_the_authors_own_breaks_win():
    """A draft written as numbered posts already has its cuts decided. The
    packer must not merge two of them into one post or split one into two."""
    text = "第一段。\n\n---\n\n第二段。\n\n---\n\n第三段。"
    assert lf.segment(text, 500) == ["第一段。", "第二段。", "第三段。"]
    assert lf.flatten(text) == "第一段。\n\n第二段。\n\n第三段。"
    lf.verify_verbatim(lf.flatten(text), lf.segment(text, 500))


def test_an_oversized_authored_block_stops_the_run():
    """Silently re-cutting it would publish a break the writer did not choose,
    and the fix is a decision about the writing."""
    text = "短。\n\n---\n\n" + "長" * 600
    with pytest.raises(ValueError, match="block 2 of 2 is 600 characters"):
        lf.segment(text, lf.THREADS_LIMIT)


def test_authored_breaks_become_blank_lines_on_x():
    """The breaks are Threads-shaped. On X the piece fits one post, so they
    cost nothing — chaining them would spend a write credit per block."""
    text = "第一段。\n\n---\n\n第二段。"
    assert lf.plan(text, ["X"])["X"] == [lf.Post("第一段。\n\n第二段。")]


def test_paragraphs_stay_whole_when_they_fit():
    text = "第一段。\n\n第二段。\n\n第三段。"
    assert lf.segment(text, 500) == ["第一段。\n\n第二段。\n\n第三段。"]
    assert lf.segment(text, 8) == ["第一段。", "第二段。", "第三段。"]


FIGURES = (
    "開頭。\n\n![【圖 1：池塘】](img/a.png)\n\n"
    "中段。\n\n![【圖 2：水面】](img/b.png)\n\n結尾。"
)


def test_each_figure_closes_an_x_post_with_its_image():
    """X takes four images a post; an article can have nine. One figure per
    post keeps every image under the paragraph the author put it after."""
    assert lf.plan(FIGURES, ["X"])["X"] == [
        lf.Post("開頭。\n\n【圖 1：池塘】", ("img/a.png",)),
        lf.Post("中段。\n\n【圖 2：水面】", ("img/b.png",)),
        lf.Post("結尾。"),
    ]


def test_threads_refuses_figures_it_cannot_attach():
    """A caption with no image under it reads as a broken post."""
    with pytest.raises(ValueError, match="figures"):
        lf.plan(FIGURES, ["Threads"])


def test_a_missing_or_wrong_image_stops_the_run_before_the_network(tmp_path):
    posts = lf.plan(FIGURES, ["X"])["X"]
    with pytest.raises(ValueError, match="image not found"):
        lf.check_images(posts, tmp_path)
    (tmp_path / "img").mkdir()
    (tmp_path / "img" / "a.png").write_bytes(b"x")
    (tmp_path / "img" / "b.png").write_bytes(b"x")
    assert lf.check_images(posts, tmp_path)[2] == []
    bad = [lf.Post("x", ("img/c.bmp",))]
    (tmp_path / "img" / "c.bmp").write_bytes(b"x")
    with pytest.raises(ValueError, match="can't take .bmp"):
        lf.check_images(bad, tmp_path)


def test_an_x_thread_with_images_posts_each_image_on_its_own_post():
    from services.twitter import TwitterService
    x = TwitterService(dry_run=True)
    assert len(x.post_thread(["a", "b"], media_ids=[["m1"], []])) == 2
    with pytest.raises(ValueError, match="2 tweets but 1 media lists"):
        x.post_thread(["a", "b"], media_ids=[["m1"]])


def test_an_image_upload_is_one_signed_multipart_post(tmp_path, monkeypatch):
    """Pins the request shape for the one X call no dry run exercises."""
    import requests
    from services.twitter import MEDIA_UPLOAD_URL, TwitterService

    seen = {}

    class Ok:
        ok = True

        def json(self):
            return {"data": {"id": "123", "media_key": "3_123"}}

    def fake_post(url, auth, files, data, timeout):
        seen.update(url=url, auth=auth, name=files["media"][0],
                    mime=files["media"][2], data=data)
        return Ok()

    monkeypatch.setattr(requests, "post", fake_post)
    img = tmp_path / "fig.png"
    img.write_bytes(b"\x89PNG")
    x = TwitterService(client=object())
    assert x.upload_image(str(img)) == "123"
    assert seen["url"] == MEDIA_UPLOAD_URL
    assert (seen["name"], seen["mime"]) == ("fig.png", "image/png")
    assert seen["data"] == {"media_category": "tweet_image"}
    assert type(seen["auth"]).__name__ == "OAuth1"
