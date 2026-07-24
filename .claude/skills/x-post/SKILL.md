---
name: x-post
description: >
  撰寫或修改 X（Twitter）post 文案時必須載入 —— 90s.pm.investing 的
  X 語氣、格式限制、「永不落 link」鐵律，以及顧問框架系列的「單一長 post」規則。
  觸發詞：X post、tweet、thread、post loop 文案、Notion drafts 的 X 平台內容、
  顧問框架（McKinsey / BCG / Bain）系列。
---

# X Post — LOOP 文案規則

## 鐵律一：X 永遠不落 link

- **不落 body**：X 演算法對外部 link 減 30–50% reach；free account 的 link post
  自 2025-03 起中位數 engagement 歸零（Buffer 18.8M post 分析）。
- **也不用「link in first reply」**：每個 reply 都消耗一次 API write，
  free tier 有 17 posts/24h、500/月 上限，補 reply 會爆額。
- **不 cross-promo 去 IG**：X 帖自成一篇完整內容，結尾落喺 insight 度，
  唔好叫人「去 IG 睇」。X 索性不落 CTA；Threads 可保留 {CTA_URL}（Substack）
  做 newsletter 連結，但唔提 IG。

## 鐵律二：顧問框架系列 = 單一長 post（X_LONGPOST）

- 一個 framework 一日一篇，**全篇一次過出喺同一個 X post 度**，唔開 reply chain。
  X Premium 上限 25,000 字元，一個長 post 足以載成套論證，只食一次 write quota；
  reply chain 每一段都食一次，容易爆額，而且中途斷開讀者流失。
- pipeline 已經幫你把一個 unit 的多段 body（用 `---` 分段）自動 join 成一個 X 長
  post；所以寫 framework 的 Thread unit 時，照 Threads 嘅分段邏輯去寫就得，
  X 出貨會自動合成一篇。
- **一定要出哂全文**：唔好只出鈎子或者頭一段。舊 pipeline 曾經只出 root，
  睇落好似講咗一半，現已改為單一長 post 出全篇。
- 長度：framework 長 post 300–600 字元屬正常、健康；比舊時 70–100 字元嘅單句
  post 長好多，因為要撐起「大名 + 三個例子 + 判斷」成套故事。唔好為咗短而砍走
  論證或者大名。

## 鐵律三：借大名做權威（顧問框架系列）

- 每篇要讓人「感覺又大名」：帶出 **McKinsey / BCG / Bain** 其中至少一個，
  講佢哋點樣用呢套框架替客戶做決定。
- 帶出框架**原作者同出處**：例如 Michael Porter、Harvard、1980 年；
  BCG matrix 出自 Bruce Henderson；Blue Ocean 出自 Kim & Mauborgne（INSEAD）。
  名 + 年份 + 出處 = 權威感，勝過空講「經典框架」。
- 大名係用嚟撐論證，唔係堆砌。一篇一到兩次自然帶到就夠，唔好每句都塞。

## 語氣

- 短句為主，但 framework 長 post 可以有節奏地鋪三個例子再收一句判斷。
- 直接：刪掉鋪墊、對沖、免責式開場，第一行就是最有料嗰句。
- 有立場：演算法獎勵 strong take；「我認為 / 我通常不會碰」可以，
  「或許可能在某程度上」不可以。
- 具體數字勝過形容詞：「1980 年」「四十年」「薄毛利」好過「很久」「很賺」。
- 第一人稱收尾：以「我睇一間公司會先……」呢類具體判斷作結，
  唔好以命令讀者（「記住」「快去做」）作結。
- 書面繁體中文；de-AI 規則見 renhua / content-anti-ai skill —— 負面對仗
  「不是A而是B」「而不是」、以及「真正 / 其實 / 關鍵在於 / 更重要的是」
  係短文最易認的 AI 味，絕對禁止。**寫完一定要過一次 renhua 掃描。**

## 格式

- Hook 行先：第一行決定一切，不設 setup。pipeline 會把選中嘅 hook 貼喺長
  post 最前，所以 hook 本身要能獨立成立、夠鈎。
- 換行：段與段之間空一行透氣（pipeline 用 `\n\n` join）；唔好牆式文字。
- Hashtags：0–2 個，放句尾；3 個以上減 ~21% engagement。

## 發文後

- 首 30–60 分鐘留守回覆：作者回覆權重 +75，like 只有 +0.5（150 倍差距）。
- 不用 engagement bait（「Retweet if you agree」）—— Grok 排名會懲罰。

## 與現有 pipeline 的關係

- units/<slug>.md 的 framework unit → generate-pending 插入 Notion →
  post loop 出貨。**新生成的 X post body 不得包含 URL**（X_INCLUDE_CTA=False）。
- X_LONGPOST=True（預設）：X 把一個 unit 的多段 body join 成一個長 post。
  Threads 照出完整 chain + {CTA_URL}。
- 舊 drafts 若 body 已帶 {CTA_URL}，X 出貨前會被 strip，唔使手動改。
