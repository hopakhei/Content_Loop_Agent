"""The one-off Threads image post: exact caption, public image URL, no Notion."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import post_threads_image as post  # noqa: E402
from config import settings  # noqa: E402

# The approved caption. Python len is 227 with the two blank lines and no
# trailing newline. The committed file must match this exactly.
APPROVED = (
    "特朗普正準備對中國、歐盟及其他 14 個經濟體實施「大規模」新關稅，消息來自《華爾街日報》。\n"
    "\n"
    "擬議關稅將涵蓋大部分進口產品；歐盟、日本及韓國的稅率料為 15% 或以下。報道指中國、越南及印度可能面對更高稅率。\n"
    "\n"
    "消息傳出後，美股回吐周一升幅。周二納斯達克收市跌 1.48%，報 23,733.54 點；標普 500 跌 0.50%，報 7,201.09 點。科技板塊跌 2.8%，半導體指數跌 7.9%；輝達收市跌 5.86%，報 155.38 美元。"
)


def test_approved_caption_file_is_unchanged():
    text = (ROOT / post.TEXT_REL).read_text(encoding="utf-8")
    assert text == APPROVED
    assert len(text) == 227
    assert post.load_post_text() == APPROVED


def test_image_file_is_the_png_screenshot():
    data = (ROOT / post.IMAGE_REL).read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert len(data) <= 8 * 1024 * 1024
    # IHDR width and height. 1920x1000 is within the Threads image limits
    # (PNG, under 8 MB, aspect ratio about 1.92:1, under the 10:1 cap).
    assert data[12:16] == b"IHDR"
    assert int.from_bytes(data[16:20], "big") == 1920
    assert int.from_bytes(data[20:24], "big") == 1000


def test_image_url_uses_the_public_card_base():
    url = post.resolve_image_url("", "https://raw.githubusercontent.com/o/r/br/")
    assert url == (
        "https://raw.githubusercontent.com/o/r/br/assets/threads/nvda-5d-yahoo-candle.png"
    )


def test_explicit_image_url_and_rejects_token_or_http():
    assert post.resolve_image_url("https://cdn.example/a.png", "") == "https://cdn.example/a.png"
    with pytest.raises(RuntimeError):
        post.resolve_image_url("", "")
    with pytest.raises(RuntimeError):
        post.resolve_image_url("http://cdn.example/a.png", "")
    with pytest.raises(RuntimeError):
        post.resolve_image_url("https://cdn.example/a.png?access_token=abc", "")


def test_altered_caption_is_refused(tmp_path):
    path = tmp_path / "post.txt"
    path.write_text(APPROVED + "。", encoding="utf-8")
    with pytest.raises(RuntimeError, match="altered"):
        post.load_post_text(path)


def _patch_settings(monkeypatch, token=""):
    monkeypatch.setattr(settings, "THREADS_ACCESS_TOKEN", token)
    monkeypatch.setattr(settings, "THREADS_USER_ID", "")
    monkeypatch.setattr(settings, "IG_CARD_URL_BASE", "https://raw.githubusercontent.com/o/r/br/")
    monkeypatch.delenv("THREADS_IMAGE_URL", raising=False)


def test_dry_run_uses_exact_text_and_does_not_need_a_token(monkeypatch):
    _patch_settings(monkeypatch, token="")
    seen = {}

    class Spy:
        def __init__(self, dry_run=False, logger=None):
            seen["dry_run"] = dry_run

        def post_post(self, text, reply_to=None, *, image_url=None):
            seen["text"] = text
            seen["reply_to"] = reply_to
            seen["image_url"] = image_url
            return "DRYRUN-TH-test"

    monkeypatch.setattr(post, "ThreadsService", Spy)
    assert post.main(["--dry-run"]) == 0
    assert seen == {
        "dry_run": True,
        "text": APPROVED,
        "reply_to": None,
        "image_url": "https://raw.githubusercontent.com/o/r/br/" + post.IMAGE_REL,
    }


def test_live_run_checks_the_image_before_publishing(monkeypatch, capsys):
    token = "super-secret-token-value"
    _patch_settings(monkeypatch, token=token)
    seen = {}

    def fake_fetch(url, logger):
        seen["fetched"] = url

    class Spy:
        def __init__(self, dry_run=False, logger=None):
            seen["dry_run"] = dry_run

        def post_post(self, text, reply_to=None, *, image_url=None):
            seen["text"] = text
            seen["image_url"] = image_url
            return "181818"

    monkeypatch.setattr(post, "assert_image_fetchable", fake_fetch)
    monkeypatch.setattr(post, "ThreadsService", Spy)
    assert post.main([]) == 0
    assert seen["dry_run"] is False
    assert seen["text"] == APPROVED
    assert len(seen["text"]) == 227
    assert seen["fetched"] == seen["image_url"]
    captured = capsys.readouterr()
    assert token not in captured.out
    assert token not in captured.err
    for path in (ROOT / "logs").glob("threads-image_*.log"):
        assert token not in path.read_text(encoding="utf-8")


def test_live_run_does_not_publish_when_the_image_is_not_public(monkeypatch, capsys):
    token = "super-secret-token-value"
    _patch_settings(monkeypatch, token=token)

    def boom(url, logger):
        raise RuntimeError(f"Meta said no for access_token={token}")

    class Spy:
        def __init__(self, dry_run=False, logger=None):
            raise AssertionError("service constructed before the image check failed")

        def post_post(self, *args, **kwargs):
            raise AssertionError("published")

    monkeypatch.setattr(post, "assert_image_fetchable", boom)
    monkeypatch.setattr(post, "ThreadsService", Spy)
    assert post.main([]) == 1
    captured = capsys.readouterr()
    assert token not in captured.out
    assert token not in captured.err
    assert "***" in captured.out
    for path in (ROOT / "logs").glob("threads-image_*.log"):
        assert token not in path.read_text(encoding="utf-8")


def test_workflow_is_a_manual_dispatch_and_does_not_touch_notion_or_loop1():
    workflow = (ROOT / ".github/workflows/post-threads-image.yml").read_text(encoding="utf-8")
    post_loop = (ROOT / ".github/workflows/post.yml").read_text(encoding="utf-8")
    assert "workflow_dispatch:" in workflow
    assert "schedule:" not in workflow
    assert "NOTION" not in workflow
    assert "secrets.THREADS_ACCESS_TOKEN" in workflow
    assert "secrets.THREADS_USER_ID" in workflow
    assert "raw.githubusercontent.com" in workflow
    # Loop 1's cron and Notion pickup stay on the original workflow.
    assert 'cron: "30 4 * * *"' in post_loop
    assert "NOTION_CONTENT_DRAFTS_DB" in post_loop
    assert "post-threads-image" not in post_loop
