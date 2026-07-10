# Instagram 接入設計（規劃）

目標：Quote Card 內容自動變成圖卡發上 Instagram，成為第三個發佈平台。
現狀缺口：LOOP 只發文字；IG 必須有圖。本文檔是實施前的設計，未寫代碼。

## 為什麼從 Quote Card 入手

每篇文章的 12 個單位裡有 3 個 Quote Card 文案（標記「全平台」），本來就是
「一句、有記憶點、可獨立成立」的圖卡文案 — 內容管線不用改，缺的只是渲染和發佈。

## 架構（跟 Threads 同一個模式）

```
Notion 草稿 (Quote Card, Platform 含 Instagram)
   │
   ├─ services/imagecard.py   Pillow 把文案渲染成 1080×1350 PNG（品牌模板）
   ├─ 圖床：commit 到 repo 的 cards/ → raw.githubusercontent.com 公開 URL
   │        （IG API 只接受公開 image_url，不接受上傳檔案）
   ├─ services/instagram.py   IG Graph API 兩步發佈：
   │        POST /{ig-user-id}/media          (image_url + caption)
   │        POST /{ig-user-id}/media_publish  (creation_id)
   │        — 與 ThreadsService 幾乎同構，重用 retry / 容器就緒輪詢
   └─ Post Performance 記錄 platform=Instagram；Loop 2 之後接 IG insights
```

## 圖卡設計規格

- 尺寸 1080×1350（4:5 直式，feed 佔屏最大）。
- 模板元素：深色底 + 品牌色點綴、大字金句（Noto Sans TC Bold，自動縮放換行）、
  右下 @90s.pm.investing、左上「90s.pm 投資 #<issue>」小標。
- Pillow 純代碼渲染，無外部服務、零成本、可在 GitHub Actions 跑。
- 先出 3-5 張樣板圖人工過目，鎖定模板再自動化。

## 帳號與憑證（你要做的一次性設定）

1. IG 帳號轉 Professional（Creator 即可）。
2. developers.facebook.com 現有 app（Threads 那個）加 **Instagram** 產品，
   用「Instagram API with Instagram Login」（新版，不需要 Facebook Page）。
3. 生成長期 token，scope：`instagram_business_basic` +
   `instagram_business_content_publish`。
4. Secrets：`IG_ACCESS_TOKEN`（+ 可選 `IG_USER_ID`，同 Threads 一樣可自動解析）。

## 發佈規則

- 每日 1 張圖卡（IG 官方 API 限額 25 posts/24h，遠夠用）；時段用 12:30 或 21:30。
- Caption = Hook + 文案 + 「完整框架 link in bio」 — IG caption 連結不可點，
  CTA 走 bio link（bio 放 Substack 連結，這是 IG 的標準漏斗）。
- 計入每日 5 posts 上限之內，作為一個 posting event。

## 分階段

| 階段 | 內容 | 驗收 |
|---|---|---|
| P1 | imagecard.py 渲染器 + 樣板圖 | 3 張樣板人工過目 |
| P2 | instagram.py + Loop 1 接入（dry-run → 實發一張） | IG 上見到圖卡 |
| P3 | IG insights 入 Loop 2（reach/likes/saves → 同一互動率框架） | 夜間報告出現 IG 行 |

## 風險

- raw.githubusercontent URL 偶爾被 Meta 抓取失敗 → 備選 GitHub Pages。
- 中文字體渲染：Noto Sans TC 需隨 repo 帶字體檔（OFL 授權，可 commit）。
- IG 對純文字圖卡的自然觸及一般 — 所以只用現成的 Quote Card 文案，
  不為 IG 額外生產內容，成本近零，觸及是白賺。
