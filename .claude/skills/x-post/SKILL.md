---
name: x-post
description: >
  撰寫或修改 X（Twitter）post 文案時必須載入 —— 90s.pm.investing 的
  X 語氣、格式限制、「永不落 link」鐵律，以及策略框架系列的「單一長 post」規則。
  觸發詞：X post、tweet、thread、post loop 文案、Notion drafts 的 X 平台內容、
  策略框架（McKinsey / BCG / Bain）系列。
---

# X Post — LOOP 文案規則

## 鐵律零：一個框架要交齊三份，唔可以淨寫 unit

寫 `units/<slug>.md` 只係餵到 X 同 Threads。同一個框架仲要有
`carousels/<slug>.json`（Instagram）同埋 `assets/background_queries.json`
入面一條 10 句 query（背景相）。三者之間冇 code 連住，做漏一份唔會報錯，
只會嗰條線靜靜地乾塘 —— 試過一次過起咗十個 carousel 但冇補 unit，X 同
Threads 就成日冇嘢出，post loop 每個時段跑兩秒收工，冇任何 error。

`tests/test_framework_parity.py` 會卡住呢件事，三份唔齊就 CI 紅。
詳情見 ig-carousel skill。

## 鐵律一：X 永遠不落 link

- **不落 body**：X 演算法對外部 link 減 30–50% reach；free account 的 link post
  自 2025-03 起中位數 engagement 歸零（Buffer 18.8M post 分析）。
- **也不用「link in first reply」**：每個 reply 都消耗一次 API write，
  free tier 有 17 posts/24h、500/月 上限，補 reply 會爆額。
- **不 cross-promo 去 IG**：X 帖自成一篇完整內容，結尾落喺 insight 度，
  唔好叫人「去 IG 睇」。X 索性不落 CTA；Threads 可保留 {CTA_URL}（Substack）
  做 newsletter 連結，但唔提 IG。

## 鐵律二：策略框架系列 = 單一長 post（X_LONGPOST）

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

## 鐵律二點五：一個框架 = 一篇旗艦 Thread

- **唔好一個框架切成 5 個 unit 連續出。** 舊做法一個框架出 Thread + 反共識 + 數據衝擊
  + Quote Card + 下集鈎子，五個 unit 講緊同一件事（同一個護城河、同一批 Costco/
  Apple/Ferrari 例子），一個時段一個咁連續出 18 個鐘 → Threads timeline 好似洗版，
  讀者以為你不斷出同一個 post。
- 數據亦都證實 rehash unit 跑輸：Thread 2.81% engagement，反共識 0.56%、
  Quote Card 0.55%、數據衝擊 0.33%。留返最強嗰篇就夠。
- 所以 units/<slug>.md **每個框架只寫一個【Thread】unit**，把整套故事（大名 + 三個
  例子 + 判斷）放晒入去。要帶下一個框架，就喺旗艦嘅最後一段輕輕帶一句 teaser，
  唔使開多一個 unit。

## 鐵律三：借大名做權威（策略框架系列）

- **歸屬要準：框架係原作者提出，唔係 McKinsey/BCG/Bain 提出。** 唔好寫成
  「McKinsey、BCG、Bain 判斷公司用的是這套框架」——會令人以為框架係佢哋整。
  正確擺法係：框架 = 原作者的（Porter / Bruce Henderson / Kim & Mauborgne…），
  而 **大名係「把它當成標準工具的重度使用者」**。例如「這套框架後來成了
  McKinsey、BCG、Bain 的第一課」、「做行業盡職調查，翻開的第一頁往往就是它」、
  「顧問接一個案子評估行業，第一張攤開的表就是這個」。
- 帶出框架**原作者同出處**：Michael Porter（Harvard，1980 三種基本策略 / 1979
  《哈佛商業評論》五力）；BCG matrix 出自 Bruce Henderson（1970）；Blue Ocean
  出自 Kim & Mauborgne（INSEAD）。名 + 年份 + 出處 = 權威感，勝過空講「經典框架」。
- **全名 trio「McKinsey、BCG、Bain」一篇只出一次**（放喺開頭做權威 hook 最好）。
  第二次要提就用代稱：「頂級顧問」「顧問界」「那幾家事務所」，唔好成個 trio 出兩次。
- 連個 idea 都唔好重複：如果開頭已經講咗「顧問攤開的第一張表」，結尾就唔好再講一次
  「盡職調查翻開的第一頁」——同一個意思換個殼講兩次，一樣係重複。結尾用第一人稱判斷收。

## 鐵律四：繁體中文書面語，台灣讀者睇得明

- 出街文案用**書面繁體**，**避免港式／粵語字眼**，令台灣讀者一樣睇得明：
  - 平（cheap）→ 便宜；割價 → 削價；打得兇 / 打得多兇 → 競爭激烈；
    全踩 → 幾乎全中；話語權 → 議價能力；最硬 → 最強；影碟 → DVD；
    兩頭不到岸 → 兩邊都討不到好 / 兩頭落空；睇 → 看；係 → 是；嗰 → 那。
  - **「講」＋題目（講波士頓矩陣）係港式**；台灣書面用「談 / 是」：
    「下一個框架是波士頓矩陣」「下一個框架，談波士頓矩陣」，唔好寫「講波士頓」。
- 專有名詞用台灣慣用譯法（視訊、串流、盡職調查、議價能力）。
- 寫完連 renhua + content-anti-ai 一齊掃：AI 味 + 港式字眼一次過清。

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
