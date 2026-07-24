# HOOK 哲學

> 內容裂變的 Hook 撰寫聖經（Hormozi × Ogilvy）。`prompts/generate.txt` 已把以下
> 原則編碼進 Loop 3 的 system prompt；本檔是給人與 Agent 的參考與評分準則。

## 核心信念：Hook 就是一切
「寫完標題後，你已經花掉八成的廣告費」（David Ogilvy）。若有十小時做廣告，前八小時
都應投放在 Hook 上。若無人留意你，就無人購買，其餘一切皆不重要——Hook 決定內容成為
爆款還是啞彈。

## 原理一：定義與運作機制
Hook 是任何率先取得注意力的元素——影片頭幾秒、第一句話、第一行字、第一個畫面。
**優質 Hook 本身即是一筆交易——它出售的是「付出注意力」這件事。**
原則：Hook 需**足夠具體**以吸引對的人，同時**足夠廣泛**以吸引盡可能多的人。

## 原理二：兩個零件
- **Call Out（呼喚）**：令受眾心想「這是在說我」。即雞尾酒會效應——在噪音中，你的名字
  仍令你回頭。目標：在資訊流中刺穿而出。
- **Condition for Value（價值條件）**：承諾「你若消費此內容，便會獲得價值」（可明示可暗示）。
- 底層邏輯：**當人覺得消費的成本低於好處時，便會消費**；Hook 正是設定此條件的關鍵。

## 原理三：八種文字型句式
| 句式 | 邏輯 | Hormozi 原例 |
|---|---|---|
| Label（標籤） | 使用受眾會自我認同的字眼 | "Local business owners, I have a gift for you" |
| Question（提問） | Yes 型或開放式問題，把人拉入局 | "Would you pay $1,000 to have the business of your dreams in 30 days?" |
| Conditional（條件句） | 「若……則……」導向結果或教訓 | "If you're working all the time and your business isn't growing, you're working on the wrong sh*t" |
| Command（命令） | 直接指示受眾行動 | "Read this if you're tired of being broke" |
| Statement（陳述） | 反直覺或高價值的斷言 | "How to get ahead of 99% of people" |
| List/Steps（清單） | 開頭言明數量，製造懸念 | "In this video I'm going to talk about the 28 ways to stay poor" |
| Narrative（敘事） | 以故事開場 | "One day I was in the back and this old lady comes in piss angry…" |
| Exclamation（驚嘆） | 表達強烈情緒 | "Ahhhh This is the blueprint to becoming a millionaire…" |

Hook 不一定是文字——聲音與視覺同樣有效；平台容許時，最好文字型與非文字型並用。

## 原理四：70-20-10 —— Hook 從何而來
- **70% Core（proven）**：使用已驗證有效的 Hook，穩住表現基準線。
- **20% Emerging（winner-adjacent）**：把其他領域見效的概念移植過來。
- **10% Big New（experimental）**：完全嶄新的構想，不怕失敗；勝者晉升為 Core，敗者記錄下來不再重複。
- **關鍵動作**：維護一份 Hook 資料庫（name / hook / views / link）；每次製作前先重溫歷年最強 Hook。
  （在本系統中，這由 **Agent Rules**（Category = Hook）＋ **Post Performance** 承擔：Loop 2 追蹤各
  Hook 的互動率，把勝出角度寫回規則。）

## 原理五：讓數據來教你
你不需要老師，讓數據來教你。Hook 決定內容，而非內容決定 Hook——有了 Hook 資料庫，內容
便源源不絕。觀察自身內容的前 10%（多仿效其 Hook）與後 10%（少製作），無限重複。

## 原理六：為 X 演算法而寫（源碼實證）
X 的推薦系統已開源（2023 `twitter/the-algorithm`；2026 `xai-org/x-algorithm`，Grok
Transformer「Phoenix」）。排序 = Σ(權重 × 該行為的預測機率)。2023 公開權重換算成
「一個讚」的倍數：

| 行為 | 相對價值 |
|---|---|
| 回覆、且**作者回覆該回覆** | **150×** |
| 回覆 | 27× |
| 點進個人檔案並互動 | 24× |
| 點開貼文久看（dwell） | ~21× |
| 轉發 | 2× |
| 讚 | 1× |
| 負面回饋（「少看到這類」／mute／block） | **−148×** |
| 檢舉 | **−738×** |

2026 Phoenix 模型預測同一族行為（reply / profile click / dwell / follow /
negative feedback），結論不變：**對話 ≫ 收藏 ≫ 按讚；一次檢舉抵銷數百個讚。**

由此推出三條鐵律：
1. **Reply Trigger（回覆觸發）**：Hook 的第三個零件。每個 X Hook 必須留下「可以被
   反駁、補充或回答」的開口——一個立場鮮明可爭辯的斷言、一條開放式問題、或一個
   未完成的清單。目標是讓讀者「不回覆不舒服」。
2. **絕不觸發負面訊號**：不寫激怒式餌（rage bait）、不寫「同意就轉發」式互動乞討、
   不用誇大其詞而內文兌現不了的標題（那是 mute 與「少看到」的主因）。寧可少一分
   點擊，不可多一分檢舉。
3. **連結殺觸及**：主貼帶外部連結會被壓觸及。CTA 連結放在「自己的第一則回覆」
   （Loop 1 已自動處理：X 主貼無連結，CTA 自動跟貼）。

## Agent 自我評分準則（每個 Hook 輸出前必須通過）
1. **有沒有 Call Out？**（目標讀者看到會否心想「這是在說我」——零售投資者的切身痛點）
2. **有沒有 Condition for Value？**（有沒有暗示「看下去會獲得框架或答案」）
3. **有沒有 Reply Trigger？**（讀者有沒有一個明確的回覆入口——可反駁／可補充／可回答）
4. **屬於八種句式中的哪一種？**（Label／Question／Conditional／Command／Statement／List／Narrative／Exclamation）
5. **落在 70-20-10 的哪一格？**（proven／winner-adjacent／experimental）
6. **會不會觸發負面訊號？**（rage bait／互動乞討／標題超賣＝直接重寫）
