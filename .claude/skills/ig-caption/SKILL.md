---
name: ig-caption
description: >
  撰寫 Instagram caption（carousel、quote card、Reel）時必須載入 ——
  125 字元 hook 規則、留言「全文」comment-to-DM 機制、hashtag 策略。
  觸發詞：caption、IG 文案、carousels/*.json 的 caption 欄。
---

# IG Caption — LOOP 文案規則

## 頭 125 字元決定一切

Feed 會在約 125 字元截斷（「…more」），大部分人不會點開。
第一句必須是整個 caption 最強的 hook —— 通常是文章的 unconventional 觀點
或最痛的數字（例：「尋找內在價值，本身就是錯的。」「我在一筆投資裡虧了 200 萬」）。

## 結構（carousel caption 標準格式）

```
<hook：一至兩句，unconventional 觀點>

<內容 tease：一段，撮要整輯的故事鏈；每 2–3 行換行透氣>

想看全文（<全文獨有內容 tease>）：留言「全文」，我 DM 給你。

全文：{CTA_URL}

#hashtags
```

- 長度 150–500 字元最佳；教育性強可到 1,000
- Caption 不重複 slides 內容 —— 補充「為什麼重要」的 framing
- `{CTA_URL}` 由 pipeline 替換為該文章的 Substack link（含 `?r=25kdss`）

## Link 的現實

- Caption 內的 URL 點不到 —— 真正可點的通道只有 bio link 和 DM
- 所以主 CTA 是「留言『全文』」：dm_loop cron 每 30 分鐘掃留言，
  自動 private reply 附上該 post 對應的文章 link（7 日回覆窗口）
- Caption 保留 `全文：<URL>` 一行，供想 copy 的讀者用

## Hashtags

- 3–5 個、高度相關；放 caption（2026 起 caption 文字供 IG Search SEO 索引）
- 輪換 2–3 套組合，不要每 post 完全相同（重複組合會被降權）
- 避開 >10M posts 的巨型 tag；50K–500K 規模的 tag 效益最好
- 現行基準：`#投資 #價值投資 #財經 #stockmarket`，可按主題加 1–2 個輪換

## 禁忌

- Engagement bait 措辭會被 IG 明文降權：「Tag someone」「Double tap if you agree」
  「Follow for more」逢 post 出現
- 「留言『全文』」屬 DM-based CTA，IG 對此類有戒心 —— 每 post 只用一次、
  語氣自然、offer（全文）必須真有價值
- 語氣：書面繁體中文、個人化；短句可斷行成獨立段；emoji 極少甚至不用（跟現行 brand 慣例）
- de-AI 規則見 content-anti-ai skill
