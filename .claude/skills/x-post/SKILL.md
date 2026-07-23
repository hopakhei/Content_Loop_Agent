---
name: x-post
description: >
  撰寫或修改 X（Twitter）post / thread 文案時必須載入 —— 90s.pm.investing 的
  X 語氣、格式限制，以及「永不落 link」鐵律。觸發詞：X post、tweet、thread、
  post loop 文案、Notion drafts 的 X 平台內容。
---

# X Post — LOOP 文案規則

## 鐵律：X 永遠不落 link

- **不落 body**：X 演算法對外部 link 減 30–50% reach；free account 的 link post
  自 2025-03 起中位數 engagement 歸零（Buffer 18.8M post 分析）。
- **也不用「link in first reply」**：每個 reply 都消耗一次 API call，
  free tier 有 17 posts/24h 上限，補 reply 會爆額。
- **不 cross-promo 去 IG**：X/Threads 帖各自獨立、自成一篇完整內容，結尾落喺
  insight 度，唔好叫人「去 IG 睇」（跨平台導流好突兀）。X 索性不落 CTA；
  Threads 可保留 {CTA_URL}（Substack）做 newsletter 連結，但唔提 IG。

## 語氣

- 短句。一句一個意思。然後下一句。
- 直接：刪掉鋪墊、對沖、免責式開場，第一行就是最有料的那句
- 有立場：演算法獎勵 strong take；「我認為」可以，「或許可能在某程度上」不可以
- 具體數字勝過形容詞：「46 億美元」好過「巨額虧損」；「25 年」好過「很長時間」
- 第一人稱：「我在這注虧了 200 萬」好過「投資者常犯此錯」
- 書面繁體中文；de-AI 規則見 content-anti-ai skill（負面對仗「不是A而是B」
  是短文最易認的 AI 味，絕對禁止）

## 格式

- 單 post：70–100 字元最佳（愈短愈易被 quote，quote 權重 = like 的 20 倍）
- Hook 行先：第一行決定一切，不設 setup
- Hashtags：0–2 個，放句尾；3 個以上減 ~21% engagement
- 換行：1–2 個位置透氣即可；不要牆式文字

## Thread（有多步結構才用，單 post 講得完就不要 thread）

- 6–8 條最佳；第 1 條必須獨立成立（大部分人不會點開）
- 一條一個 idea：任何一條被 screenshot 都要 make sense
- 不開「🧵」「A thread on…」；不收「End of thread」—— 直接開始，直接結束
- 倒數第二條放 proof（一個真實數字）；最後一條一句總結
- 全部寫好才發第一條；3–5 分鐘內發完整條 thread

## 發文後

- 首 30–60 分鐘留守回覆：作者回覆的權重 +75，like 只有 +0.5（150 倍差距）
- 不用 engagement bait（「Retweet if you agree」）—— Grok 排名會懲罰；
  被大量 mute/block/report 的帳號食 -369x 權重

## 與現有 pipeline 的關係

- post loop（generate.yml / post workflow）產生的 X drafts 應遵守本規則：
  **新生成的 X post body 不得包含 URL**。
- 舊 drafts 若 body 已帶 {CTA_URL}，出貨前應以 IG 導流句取代，不要照發。
