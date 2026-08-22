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


def test_select_hook_winner_override_beats_pooled_rule():
    d = _draft(hooks={"A": "a", "B": "b", "C": "c"})
    rules = Rules(best_hook_type="C")           # pooled says C
    rng = random.Random(42)
    picks = [select_hook(d, rules, rng, winner_override="A")[0] for _ in range(400)]
    assert picks.count("A") > picks.count("C")  # per-platform override wins
    assert picks.count("A") > picks.count("B")


def test_compose_single_appends_bare_link_when_missing():
    d = _draft(content_type="反共識", post_body="市場不是賭場。")
    posts = compose_posts(d, hook_text=None, cta_url=CTA)
    assert len(posts) == 1
    assert posts[0].startswith("市場不是賭場。")
    # The CTA is a bare link — no sell copy, no 👉.
    assert posts[0].rstrip().endswith(CTA)
    assert "👉" not in posts[0] and "完整框架" not in posts[0]


def test_compose_softens_baked_in_sell_copy_cta():
    body = "市場不是賭場。\n\n完整框架＋案例在 Substack 👉 " + CTA
    d = _draft(content_type="反共識", post_body=body)
    posts = compose_posts(d, hook_text=None, cta_url=CTA)
    assert "👉" not in posts[0] and "完整框架" not in posts[0]
    assert posts[0].count(CTA) == 1
    assert posts[0].rstrip().endswith(CTA)


def test_compose_swaps_baked_cta_to_platform_destination():
    # A baked-in Substack sell line composes to the PLATFORM's CTA when a
    # different destination is passed (e.g. the GitHub repo on X).
    body = "主體。\n\n完整框架＋案例在 Substack 👉 https://old.example/p/1?r=x"
    d = _draft(content_type="反共識", post_body=body)
    posts = compose_posts(d, hook_text=None, cta_url="https://github.com/Draw-Tree/tree-quant-ledger")
    assert posts[0].rstrip().endswith("https://github.com/Draw-Tree/tree-quant-ledger")
    assert "old.example" not in posts[0]
    assert "👉" not in posts[0]


def test_compose_substitutes_placeholder_to_bare_link():
    d = _draft(content_type="反共識", post_body="主體\n\n完整框架＋案例在 Substack 👉 {CTA_URL}")
    posts = compose_posts(d, hook_text=None, cta_url=CTA)
    assert "{CTA_URL}" not in posts[0]
    assert "👉" not in posts[0] and "完整框架" not in posts[0]
    assert posts[0].count(CTA) == 1


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


def test_compose_hook_echo_differing_by_punctuation_is_not_printed_twice():
    # The original guard used `startswith` on raw text, so one comma of
    # copy-editing between the hook and the body's opening was enough to ship
    # the sentence twice. The real profit-formula pair: 「月底結帳時，未必」 in the
    # hook against 「月底結帳時未必」 in the body.
    hook = "你每天經過那間排隊最長的早餐店，月底結帳時，未必是這條街上留下最多錢的一家。"
    body = ("你每天經過那間排隊最長的早餐店，月底結帳時未必是這條街上留下最多錢的一家。"
            "收入模式是一份蛋餅三十五元。")
    posts = compose_posts(_draft(content_type="Thread", post_body=body),
                          hook_text=hook, cta_url=None)
    assert posts[0].count("排隊最長的早餐店") == 1
    assert posts[0].startswith("你每天經過那間排隊最長的早餐店")
    assert posts[0].endswith("收入模式是一份蛋餅三十五元。")


def test_compose_hook_echo_spanning_two_sentences_is_not_printed_twice():
    # Hook B is often the body's first *two* sentences, so a guard that only
    # ever looked at one would still leave the reader a repeat.
    hook = "你家樓下兩間理髮店收一樣的價錢，一間排到要預約，一間常常沒人，撐了兩年就收。"
    body = ("你家樓下兩間理髮店收一樣的價錢。一間排到要預約，一間常常沒人，撐了兩年就收。"
            "同樣的價位，客人心裡拿到的完全不同。")
    posts = compose_posts(_draft(content_type="Thread", post_body=body),
                          hook_text=hook, cta_url=None)
    assert posts[0].count("兩間理髮店") == 1
    assert posts[0].count("撐了兩年就收") == 1
    assert posts[0].endswith("同樣的價位，客人心裡拿到的完全不同。")


def test_compose_keeps_the_half_only_the_body_has():
    # The body's first sentence contains the hook and adds to it. Dropping the
    # sentence would lose the added half; prepending would print the shared
    # half twice. The body alone is the only option that does neither.
    hook = "月底看帳單，你會發現有幾筆錢每個月照扣，但你講不出它替你做過什麼。"
    body = ("月底看帳單，你會發現有幾筆錢每個月照扣，但你講不出它替你做過什麼；"
            "也有幾筆你嫌貴，卻怎樣都捨不得停。錢分去哪，比嘴上說重視什麼誠實。")
    posts = compose_posts(_draft(content_type="Thread", post_body=body),
                          hook_text=hook, cta_url=None)
    assert posts[0] == body
    assert posts[0].count("每個月照扣") == 1
    assert "也有幾筆你嫌貴" in posts[0]


def test_compose_drops_echo_when_hook_says_more_than_the_body_sentence():
    # The hook continues past what the body repeats, so overall similarity never
    # clears the restatement bar — the sentence is still already in the hook.
    hook = "朋友問你上週那間餐廳好不好吃，你遲疑了半秒。那半秒的重量，有人拿它蓋出了一整套方法。"
    body = ("朋友問你上週那間餐廳好不好吃，你遲疑了半秒。"
            "那半秒裡發生的事，是你在衡量要不要把自己的信用押上去。")
    posts = compose_posts(_draft(content_type="Thread", post_body=body),
                          hook_text=hook, cta_url=None)
    assert posts[0] == f"{hook}\n\n那半秒裡發生的事，是你在衡量要不要把自己的信用押上去。"


def test_compose_keeps_the_scene_when_the_hook_is_about_something_else():
    # Arm A opens on the reader's holding; the body still has to open on the
    # everyday scene 鐵律零點六 asks for. A short sentence sharing a few
    # characters with the hook must not delete it.
    hook = "你買一間公司的股票之前，先問自己講不講得出它靠什麼賺錢。"
    body = "你樓下那間咖啡店，你天天經過，甚至每週買兩次。它靠什麼賺錢？多數人會說賣咖啡。"
    posts = compose_posts(_draft(content_type="Thread", post_body=body),
                          hook_text=hook, cta_url=None)
    assert posts[0] == f"{hook}\n\n{body}"


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
    # A bare-link CTA line is stripped when the URL is provided.
    assert strip_cta([f"body\n{CTA}"], CTA) == ["body"]
    # Legacy 👉 marker still recognised even without the URL passed in.
    assert strip_cta(["body\n完整框架 👉 x"]) == ["body"]


def test_strip_cta_never_returns_empty():
    posts = [CTA_TEMPLATE.format(url=CTA)]
    assert strip_cta(posts, CTA) == posts


def test_length_warnings():
    assert length_warnings(["x" * 281]) != []
    assert length_warnings(["short"]) == []
