# 外部去 AI 味 skill：借鑒與取捨

自家的 checklist 寫得早，抓得住「詞」同「句」，但抓唔到**成篇文嘅骨架**同**成個 corpus 嘅重複**。
呢個 folder 收埋外面兩份出名嘅中文去 AI 味 skill 做參考，同埋記低我哋抄咗邊幾條、
邊幾條**故意唔抄**。

## 收錄

`writing-humanizer/` — shyuan/writing-humanizer，MIT licensed，
commit `b8cb8a5`，2026-08 抓落嚟。原始碼：https://github.com/shyuan/writing-humanizer

31 個 pattern，分六個 reference 檔。1–24 由英文檢測清單翻譯過嚟（Wikipedia
《Signs of AI writing》，WikiProject AI Cleanup 維護），25–31 係作者自己針對
**中文論說文**加嘅——嗰七條先至係我哋缺嘅嗰部分。繁體、台灣讀者取向，同呢條
channel 嘅出版語言啱。

`LICENSE` 原封不動保留。改咗嘅話要標明；我哋冇改，淨係抄咗規則入自己嘅 SKILL.md。

## 冇收錄但睇過

- **op7418/Humanizer-zh**（https://github.com/op7418/Humanizer-zh）— 24 個 pattern，
  同上面 1–24 同源。冇收，因為重複。但佢五條 core rule 入面有一條值得記低：
  **「變化節奏：長短句交錯、兩項好過三項、段落結尾要變」**。最後嗰半句
  正正命中我哋 corpus 最大嗰個問題（見下）。
- redbaronyyyyy-eng/humanizer-zh-academic — 學術論文取向，唔啱社交平台短文。
- ai-zixun/humanizer-zh、B1lli/remove-ai-flavor-writing-skill — 簡體，規則同上面重疊。
- makotofalcon/humanizer-ja — 日文。
- laolaoshiren/claude-code-skills-zh — skill 合集，入面嘅去 AI 味嗰個係上面其中一份嘅 fork。

## 抄咗入 SKILL.md 嘅四條

揀嘅準則唔係「規則好唔好」，係「我哋而家真係犯緊」。2026-08-16 掃過全部 34 篇 unit：

| 借鑒 | 上游編號 | corpus 實測 |
|---|---|---|
| 破折號過度 | 模式 13（兩份都有） | 149 個 ——，中位數 4／篇，最多 core-vs-non-core 9 個 |
| 三段式法則過度 | 模式 10 | 126 組「X、Y、Z」，最多 relative-cost-positioning 10 組 |
| 段落結尾要變 | Humanizer-zh core rule 3 | 34 篇有 31 篇用「下一個框架…」收，17 篇尾段用「我／我自己…」開 |
| 意義蓋章式收尾 | 模式 27 | 同上，收尾套語化就係呢個病嘅中文變種 |

四條都寫成 `scripts/audit_style.py` 嘅硬檢查，唔靠人記得。

## 故意唔抄嘅

- **模式 10 講「必須改為兩項或四項」** — 我哋照抄會撞正框架本身。五力就係五個，
  7S 就係七個 S，Kano 三個籃子。真實嘅列舉唔係 rule-of-three，唔可以因為
  數字啱三就斬。checker 只數**修辭性**嘅三項並列（`X、Y、Z` 呢種句內排比），
  而且設上限唔設禁令。
- **模式 14／15／16／17（粗體、內嵌標題、emoji、引號）** — X 同 Threads 出嘅係
  純文字，本身冇粗體；emoji 喺 ig-caption skill 已經另有規矩。
- **模式 25／26（大綱骨架、四字標籤清單）** — 鐵律二點六（五段）已經處理咗。
- **模式 31（「一條線」具象化）** — 要三個信號齊先算，誤殺風險高過收益，
  而且 corpus 掃過冇中。留喺參考檔，唔入 checker。
- **模式 18–24（chatbot 痕跡、knowledge cutoff、諂媚語氣）** — 呢啲係 chat 輸出
  嘅病，出街文案唔會有。
