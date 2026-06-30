import random

from core.composition import (
    CTA_TEMPLATE,
    compose_posts,
    effective_cta_url,
    length_warnings,
    select_hook,
    split_thread,
)
from core.models import Draft, Rules

CTA = "https://90spm.substack.com/p/102?r=abc"


def _draft(**kw):
    return Draft(id="d1", **kw)


def test_effective_cta_prefers_override():
    d = _draft(cta_url="https://override.example")
    assert effective_cta_url(d, CTA) == "https://override.example"
    assert effective_cta_url(_draft(), CTA) == CTA
    assert effective_cta_url(_draft(), None) is None


def test_select_hook_returns_available_only():
    d = _draft(hooks={"A": "", "B": "boom", "C": ""})
    key, text = select_hook(d, rng=random.Random(1))
    assert key == "B" and text == "boom"


def test_select_hook_none_when_empty():
    assert select_hook(_draft(hooks={"A": "", "B": "", "C": ""})) == (None, None)


def test_select_hook_biases_to_winner():
    d = _draft(hooks={"A": "a", "B": "b", "C": "c"})
    rules = Rules(best_hook_type="C")
    rng = random.Random(42)
    picks = [select_hook(d, rules, rng)[0] for _ in range(400)]
    assert picks.count("C") > picks.count("A")
    assert picks.count("C") > picks.count("B")


def test_compose_single_appends_cta_when_missing():
    d = _draft(content_type="反共識", post_body="市場不是賭場。")
    posts = compose_posts(d, hook_text=None, cta_url=CTA)
    assert len(posts) == 1
    assert CTA in posts[0]
    assert posts[0].startswith("市場不是賭場。")


def test_compose_does_not_duplicate_existing_cta():
    body = f"市場不是賭場。\n\n{CTA_TEMPLATE.format(url=CTA)}"
    d = _draft(content_type="反共識", post_body=body)
    posts = compose_posts(d, hook_text=None, cta_url=CTA)
    assert posts[0].count("👉") == 1


def test_compose_substitutes_placeholder():
    d = _draft(content_type="反共識", post_body="看這裡 👉 {CTA_URL}")
    posts = compose_posts(d, hook_text=None, cta_url=CTA)
    assert "{CTA_URL}" not in posts[0]
    assert CTA in posts[0]


def test_compose_substitutes_bracket_placeholder():
    # Real drafts end the CTA with the human placeholder [連結].
    d = _draft(content_type="反共識", post_body="主體\n\n完整框架＋案例在 Substack 👉 [連結]")
    posts = compose_posts(d, hook_text=None, cta_url=CTA)
    assert "[連結]" not in posts[0]
    assert posts[0].count("👉") == 1
    assert CTA in posts[0]


def test_compose_prepends_hook():
    d = _draft(content_type="反共識", post_body="主體內容")
    posts = compose_posts(d, hook_text="反共識鈎子", cta_url=CTA)
    assert posts[0].startswith("反共識鈎子")


def test_thread_split_on_dashes():
    body = "第一條\n---\n第二條\n---\n第三條"
    assert split_thread(body) == ["第一條", "第二條", "第三條"]


def test_thread_appends_cta_as_new_tweet():
    d = _draft(content_type="Thread", post_body="鈎子\n---\n論點\n---\n收尾")
    posts = compose_posts(d, hook_text=None, cta_url=CTA)
    assert len(posts) == 4
    assert CTA in posts[-1]


def test_length_warnings():
    assert length_warnings(["x" * 281]) != []
    assert length_warnings(["short"]) == []
