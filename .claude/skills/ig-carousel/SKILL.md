---
name: ig-carousel
description: >
  製作或修改 90s.pm.investing 的 Instagram carousel（輪播圖）時必須載入。
  涵蓋 slide script 結構、經人手審批定下的編輯規矩（self-contained、一條主軸、
  概念名做標題）、渲染字數限制，以及 render → preview → 批准 → dispatch 的出貨流程。
  觸發詞：carousel、輪播、拆文做 IG series、carousels/*.json、出圖 preview、「NNN 出」。
---

# IG Carousel — LOOP 出貨手冊

## 出貨流程（每一步都不可跳過）

1. Slide script 寫在 `carousels/<issue>.json`
2. 本地渲染驗證：
   ```
   python -c "
   from services.imagecard import load_carousel_spec, render_carousel
   spec = load_carousel_spec('carousels/<issue>.json')
   render_carousel(spec, '<scratchpad>/carousel-<issue>')"
   ```
3. 用 SendUserFile 將全部 slides 交用戶過目 —— **未批准絕不出貨**
4. 用戶回覆「NNN 出」／「ok」即為批准 → dispatch workflow `instagram.yml`，
   input `carousel_issue=<issue>`，branch `claude/loop-product-spec-y45pgi`
5. 等 runner 完成，從 job log 確認 `POSTED ✓ IG CAROUSEL ... media_id=...` 後回報

修改後必須 commit + push（先 `git fetch` + `rebase`，bot 會定期推 card commit）。

## Spec 結構

```json
{
  "issue": "106",
  "cta_url": "https://90spminvesting.substack.com/p/...?r=25kdss",
  "caption": "...（{CTA_URL} 會被替換；規則見 ig-caption skill）",
  "slides": [
    {"kind": "cover", "kicker": "90s.pm 投資 · #NNN 主題", "head": "...", "sub": "..."},
    {"kicker": "01 · 分類", "head": "...", "body": "..."},
    {"kind": "cta", "bookmark": false, "head": "...", "body": "...",
     "follow": "留言「全文」，我 DM 給你", "link": "@90s.pm.investing · #NNN 主題"}
  ]
}
```

2–10 張；標準 10 張（cover + 8 內容 + CTA）。

## 策略框架系列（framework carousels）額外規矩

- **大名背書（authority hook）**：系列整體定位為「拆解顧問界（McKinsey、BCG、Bain）
  幾十年在用的思考框架」——放在 caption 開頭與封面副題，借大名建立權威。
- **準確第一**：每個 framework 標「真實」出處。當出處真係 McKinsey / BCG / Bain
  或知名學者（Porter、Christensen、Kim & Mauborgne…）時，把這個名字升做 hook
  （封面副題／起源 slide／caption）。**絕不把學者框架屈落顧問公司**——目標觀眾
  一眼睇穿，反而摧毀 credibility。學者框架照樣可借「成為所有頂級顧問公司的通用語言」
  這類「被誰採用」的真實陳述來沾大名的光。
- **投資角度**：每個 framework 都拉回投資決定（判斷護城河、拆解估值、看清風險），
  與「畫樹／MECE」一脈相承——這是 90s.pm.investing 的存在理由，不是純顧問教材。
- kicker 用「顧問框架 NN」標明系列身份。
- 版權：概念公開可教，但一律用品牌語氣重寫成故事，**不抄 Umbrex 原書句子**。

## 編輯規矩（用戶逐輯 review 定下，全部必守）

- **標題鏈原則**：每張 slide 的大題必須獨立講出該段的中心思想；
  把十個標題連起來讀，要已經是一個完整的故事。寫完 spec 後先淨讀標題鏈
  自我檢查，講不通就重排。讀者是先掃標題才決定讀 body 的。
- **Self-contained**：不得引用「上一篇」。觀眾未必看過之前的 post。
  每個案例要有一兩句背景（公司、年份、發生了什麼）才可使用。
- **一條主軸**：整輯只講文章的 unconventional 觀點；細節讓給全文。
  與主軸無關的 slide 整張刪掉，不要捨不得。
- **概念名放大做標題**：大題寫「凱利公式」「Active Portfolio Management」「DDM：不派息就值零」，
  公式本身縮到 body 一筆帶過。分類先行（例：估值法先歸類為資產法／收入法／市場法，再逐把講）。
- **注重故事，不是操作**：講來歷、點解有用（歷史背景、發明人、實戰戰績），
  不做計算 walkthrough。
- **轉折要有橋**：slide 之間一步扣一步；上一張的結尾句預告下一張。
  審稿時逐條轉折讀一次，突兀即改。
- **概念先解釋後使用**（例：MECE 要先講是什麼）。
- **第一人稱「我」**增加代入感；真實虧損／錯誤經歷是最強的 hook。
- **起承轉合**：中後段要有 climax（最痛的例子，如 Cisco 25 年），結尾扣回開頭。
- **用詞**：「內在價值」不用「真值」；書面繁體中文；de-AI 規則見 content-anti-ai skill。

## 渲染限制（imagecard.py）

- Cover head F116：每行 ≤7 個中文字，用 `\n` 手動斷行；忌孤懸標點
- Content head F88：每行 ≤10 個中文字；英文/公式較窄可稍長（如 `IR = IC × √BR`）；
  長英文名用 `\n` 斷做兩行（如 `Active Portfolio\nManagement`）
- Body：60–110 個字；渲染器會保持英文單詞完整並套用中文標點禁則
- Kicker 格式「NN · 分類」；同類 slide 重複同一分類字眼以加強 grouping
- CTA slide 設 `"bookmark": false`（用 tick 圖示）

## 演算法要點（Buffer 9.6M post 研究，2026）

- 封面承擔 ~80% 成敗：5–8 字 hook + curiosity gap，必須獨立成立
- 一張 slide 一個 idea，5 秒內讀完；超過就拆
- Saves 是最強排名信號：CTA 引導收藏（我們用 bookmark 圖示 + 留言全文 DM）
- Carousel 有獨家 second-chance 派發：沒滑完的觀眾會被再派一次
- 出 post 後首 30–60 分鐘的互動決定擴散；有留言盡快回覆
