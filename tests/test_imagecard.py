"""imagecard: card_quote text extraction, and a real render smoke test.

The render smoke test needs a CJK font. It runs locally (bundled asset /
system Noto) and skips cleanly on a bare runner without fonts — the render
path is also exercised by instagram.yml's own dry-run once merged.
"""
import pytest

from services import imagecard


def _font_or_skip():
    try:
        return imagecard._font_path()
    except RuntimeError:
        pytest.skip("no CJK font available on this host")


def test_card_quote_strips_cta_and_link_lines():
    body = "止蝕唔係紀律。\n我哋公開每一步。\n\n👉 完整框架在 Substack\n{CTA_URL}\nhttps://x/y"
    q = imagecard.card_quote(body)
    assert "止蝕唔係紀律" in q and "我哋公開每一步" in q
    assert "{CTA_URL}" not in q and "👉" not in q and "http" not in q


def test_card_quote_empty_body_is_empty():
    assert imagecard.card_quote("") == ""
    assert imagecard.card_quote(None) == ""


def test_render_card_writes_a_valid_png(tmp_path):
    _font_or_skip()
    out = tmp_path / "card.png"
    imagecard.render_card("止蝕唔係紀律。\n我哋公開每一步，錯咗就認。", "201", str(out))
    assert out.exists()
    data = out.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"     # PNG magic
    assert len(data) > 1000                       # a real rendered image


def test_load_carousel_spec_validates(tmp_path):
    import json

    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"slides": [{"head": "only one"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="2-10"):
        imagecard.load_carousel_spec(bad)

    ok = tmp_path / "ok.json"
    ok.write_text(json.dumps({"slides": [{"kind": "cover", "head": "h"},
                                         {"kind": "cta", "head": "s"}]}), encoding="utf-8")
    assert len(imagecard.load_carousel_spec(ok)["slides"]) == 2


def test_render_carousel_writes_all_slides(tmp_path):
    _font_or_skip()
    spec = {"slides": [
        {"kind": "cover", "kicker": "90s.pm · #102", "head": "測試封面", "sub": "副題"},
        {"kicker": "01 · 論點", "head": "標題一", "body": "內文一段。"},
        {"kind": "cta", "head": "先 Save", "body": "收尾", "follow": "Follow @x", "link": "bio"},
    ]}
    paths = imagecard.render_carousel(spec, str(tmp_path / "car"))
    assert [p.split("/")[-1] for p in paths] == ["01.png", "02.png", "03.png"]
    for p in paths:
        data = open(p, "rb").read()
        assert data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) > 1000
