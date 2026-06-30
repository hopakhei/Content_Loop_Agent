from core.parsing import (
    map_content_type,
    map_platforms,
    map_source_article,
    parse_units,
)

SAMPLE = """論點地圖：
- 論點一：北極星指標
- 論點二：複利

---
【1】【框架拆解 Thread（6 條推文）】【X + Threads】
Hook A（反共識）：你以為的分散投資其實是偽分散。
Hook B（數據衝擊）：90% 散戶死在這一步。
Hook C（懸念缺口）：有一個指標，機構天天看，你卻沒聽過。
Post Body：第一條鈎子
---
論點推導
---
完整框架＋案例在 Substack 👉 {CTA_URL}
---
【2】【反共識短貼 A】【Threads / X】
Hook A（反共識）：止損不是紀律，是逃避。
Hook B（數據衝擊）：設止損的人，長期回報更低。
Hook C（懸念缺口）：真正的風險控制在下單之前。
Post Body：反共識的主體論述。
---
【6】【Quote Card 文案 A】【全平台】
Hook A（反共識）：A 句
Hook B（數據衝擊）：B 句
Hook C（懸念缺口）：C 句
Post Body：一句可獨立成立的金句。
---
"""


def test_parse_unit_count():
    units = parse_units(SAMPLE)
    assert [u.number for u in units] == [1, 2, 6]


def test_parse_hooks_and_body():
    u = parse_units(SAMPLE)[1]
    assert u.hooks["A"] == "止損不是紀律，是逃避。"
    assert u.hooks["B"] == "設止損的人，長期回報更低。"
    assert u.hooks["C"] == "真正的風險控制在下單之前。"
    assert u.post_body == "反共識的主體論述。"


def test_parse_thread_body_keeps_separators():
    u = parse_units(SAMPLE)[0]
    assert "第一條鈎子" in u.post_body
    assert "論點推導" in u.post_body


def test_map_content_type():
    assert map_content_type("框架拆解 Thread（6 條推文）") == "Thread"
    assert map_content_type("反共識短貼 A") == "反共識"
    assert map_content_type("數據衝擊貼 B") == "數據衝擊"
    assert map_content_type("Quote Card 文案 A") == "Quote Card"
    assert map_content_type("故事貼") == "故事貼"
    assert map_content_type("偽科學/反面教材拆解貼") == "偽科學拆解"
    assert map_content_type("金句裂變貼") == "金句裂變"
    assert map_content_type("下集鈎子貼") == "下集鈎子"


def test_map_platforms():
    assert map_platforms("全平台") == ["X", "Threads"]
    assert map_platforms("X + Threads") == ["X", "Threads"]
    assert map_platforms("Threads / X") == ["X", "Threads"]
    assert map_platforms("Threads") == ["Threads"]


def test_map_source_article():
    assert map_source_article(102) == "102 - 北極星"
    assert map_source_article("105") == "105 - 畫樹"
    assert map_source_article(999) is None
