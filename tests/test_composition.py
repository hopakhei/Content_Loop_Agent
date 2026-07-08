import random

from core.composition import (
    CTA_TEMPLATE,
    compose_posts,
    effective_cta_url,
    length_warnings,
    select_hook,
    split_thread,
    strip_cta,
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


def test_compose_skips_hook_already_leading_the_body():
    # Some drafts' Post Body opens with Hook A's exact text — prepending it
    # again would post the same sentence twice.
    hook = "大多數財經內容，根本不是為了幫你做決策而寫的。"
    d = _draft(content_type="反共識", post_body=f"{hook}\n它是為了讓結論更容易被接受。")
    posts = compose_posts(d, hook_text=hook, cta_url=CTA)
    assert posts[0].count(hook) == 1
    assert posts[0].startswith(hook)


def test_thread_split_on_dashes():
    body = "第一條\n---\n第二條\n---\n第三條"
    assert split_thread(body) == ["第一條", "第二條", "第三條"]


def test_thread_split_on_emdashes():
    # Real drafts use an em-dash rule line as the separator.
    body = "第一條\n———\n第二條\n———\n第三條"
    assert split_thread(body) == ["第一條", "第二條", "第三條"]


def test_thread_does_not_split_on_blank_lines():
    # Blank lines inside a tweet must NOT fragment it (the over-splitting bug).
    body = "第一段\n\n第二段\n\n第三段"
    assert split_thread(body) == [body]


def test_thread_ignores_inline_dashes():
    # An em-dash inside a sentence is not a separator.
    body = "差不了多少——但倉位管理差很多。"
    assert split_thread(body) == [body]


def test_thread_appends_cta_as_new_tweet():
    d = _draft(content_type="Thread", post_body="鈎子\n---\n論點\n---\n收尾")
    posts = compose_posts(d, hook_text=None, cta_url=CTA)
    assert len(posts) == 4
    assert CTA in posts[-1]


def test_strip_cta_removes_inline_cta_line():
    posts = [f"主體內容\n\n{CTA_TEMPLATE.format(url=CTA)}"]
    out = strip_cta(posts, CTA)
    assert out == ["主體內容"]


def test_strip_cta_drops_a_threads_dedicated_cta_tweet():
    posts = ["第一條", "第二條", CTA_TEMPLATE.format(url=CTA)]
    assert strip_cta(posts, CTA) == ["第一條", "第二條"]


def test_strip_cta_leaves_link_free_posts_unchanged():
    assert strip_cta(["no cta here"], CTA) == ["no cta here"]
    # Recognises the 👉 marker even without the URL passed in.
    assert strip_cta([f"body\n{CTA_TEMPLATE.format(url=CTA)}"]) == ["body"]


def test_strip_cta_never_returns_empty():
    posts = [CTA_TEMPLATE.format(url=CTA)]
    assert strip_cta(posts, CTA) == posts


def test_length_warnings():
    assert length_warnings(["x" * 281]) != []
    assert length_warnings(["short"]) == []
