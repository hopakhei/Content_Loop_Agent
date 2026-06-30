# LOOP — LLM-Operated Output Pipeline

Content distribution engine for **90s.pm.investing**. Each Substack long-form
essay is "fissioned" into ~12 social units and posted to X on a schedule, to
amplify reach and drive Substack subscriptions.

> Core belief: *good content × systematic distribution > good content × manual distribution.*

This repo implements the **Product Spec v2.1**. Phase 1 (Loop 1 — POST) is the
priority and is production-ready; Loops 2 (LEARN) and 3 (GENERATE) are implemented
to the same spec.

---

## The three loops

```
Loop 1 — POST      讀草稿 → 發佈 → 標記已發        (cron, 5×/day)
Loop 2 — LEARN     讀數據 → 分析 → 更新規則        (cron, 02:00 HKT)
Loop 3 — GENERATE  讀文章 → 裂變 → 寫入草稿庫        (manual, per article)
```

Each loop runs independently and never blocks the others. **Notion is the single
source of truth**; the loops only read and write Notion + X.

---

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in NOTION_TOKEN, X_* keys, etc.

# Loop 1 — simulate everything, never touch X (still reads Notion):
python main.py --loop 1 --dry-run

# Loop 1 — post for the current cron slot, headless (skip the countdown):
python main.py --loop 1 --yes

# Loop 1 — force a specific slot:
python main.py --loop 1 --slot 12:30

# Loop 2 — nightly analysis:
python main.py --loop 2 [--dry-run]

# Loop 3 — fission one article into drafts:
python main.py --loop 3 --issue 102 --article-file ./article.txt [--dry-run]
```

Every run writes a timestamped log to `logs/` and echoes to stdout.

---

## Loop 1 — POST (detail)

Triggered once per cron slot (07:30 / 10:00 / 12:30 / 18:30 / 21:30 HKT). On
each run it:

1. Reads the daily quota from **Posting Rules** (falls back to `DAILY_HARD_LIMIT`).
2. Counts how many posts already went out today (HKT) from **Post Performance**.
3. Selects up to `MAX_POSTS_PER_RUN` drafts by the **priority ladder**:
   1. A draft whose precise `Scheduled Date` matches this slot.
   2. A `Scheduled` draft — round-robin across Articles, picking the one with the
      fewest posts today and respecting `Target Posts Per Day`.
   3. A `Draft`-status draft, by `Argument #` ascending.
   4. Daily limit reached → skip and log.
4. Inherits the CTA URL from the related Article (draft `CTA URL` is an override).
5. Composes the post text (see **Composition model**), picks a Hook variant.
6. Publishes to X (threads become a reply chain).
7. Flips the draft `Status → Posted` and creates a **Post Performance** row
   (`Post ID`, `Posted At`, `Platform`, `Hook Used`).

**Irreversibility guards:**
- `--dry-run` simulates the full flow but never posts to X or writes to Notion.
- Before each real post the console shows a preview and waits
  `PREVIEW_COUNTDOWN_SECONDS` (default 5s) so you can `Ctrl+C`. `--yes` skips the
  wait for headless cron.

Phase 1 publishes to **X only** (the configured publishing layer). Threads-only
drafts (e.g. 故事貼, 金句裂變) are skipped with a log line until a Threads
publisher exists.

### Composition model

`Post Body` is the canonical content. The three `Hook` fields are *alternative
opening lines* used by the A/B/C experiment.

- **Hook**: Loop 1 picks one hook variant (weighted toward the winning hook from
  Posting Rules, else random among the non-empty hooks) and prepends it to the
  first post/tweet. If no hook fields have text, the body is posted as-is.
- **CTA**: effective URL = draft override → else Article CTA URL.
  - If the body contains the literal `{CTA_URL}` placeholder, it is substituted.
  - Otherwise, if no CTA is present, the standard line is appended:
    `完整框架＋案例在 Substack 👉 {url}` (a new final tweet for threads).
- **Threads**: a `Thread` body is split into individual tweets on a line
  containing only `---` (falls back to blank-line splitting).

---

## Loop 2 — LEARN (detail)

Nightly (02:00 HKT). Refreshes engagement metrics for posts older than 24h via
the X API, then aggregates **engagement rate** = `(likes + replies + reposts) /
impressions` over a 30-day window, grouped by slot / content type / hook. With at
least **20 data points** it writes the winners back into **Posting Rules**, which
Loop 1 then reads on its next run. The A/B/C hook design biases Loop 1 toward the
winning hook while continuing to explore the others.

---

## Loop 3 — GENERATE (detail)

Manual, per article. Sends the article's full text through the starter prompt in
`prompts/generate.txt` (filling `{ISSUE_NUMBER}`, `{CTA_URL}`, `{ARTICLE_FULL_TEXT}`),
parses the 12 units out of Claude's response, maps their labels to the Notion
select/multi-select options, and inserts them into **Content Drafts** (Status =
`Draft`, Generation = 1) related to the Article.

Default model is `claude-opus-4-8` (override with `CLAUDE_MODEL`).

---

## Notion schema (live)

Property names in `config/schema.py` mirror the **live** databases, which differ
slightly from the spec prose. Notable points:

| Spec says | Reality (used by the code) |
|---|---|
| Content Drafts has `Post ID` / `Posted At` | They live on **Post Performance**; Loop 1 creates that row. Content Drafts only flips `Status`. |
| `Hook A/B/C` | `Hook A 反共識`, `Hook B 數據衝擊`, `Hook C 懸念缺口` |
| Performance Log | DB is titled **Post Performance**; `Post ID` is its **title** property. |
| `Hook Used` values | `A - 反共識`, `B - 數據衝擊`, `C - 懸念缺口` |
| Posting Rules DB | No ID in the spec; created under the Content Hub (`f10d0491-…`) and wired into config. |

### Posting Rules database

Created under **90s.pm.investing — Content Hub** with the schema below and seeded
with one `LOOP Auto Rules` row (Daily Limit 5, all slots, no hook bias yet). Its
data-source ID `f10d0491-d1a8-4cd6-9e87-5f47f554cbe6` is baked into `.env.example`
and the workflows. Loop 2 writes it; Loop 1 reads it. If unset, Loop 1 still falls
back to `DAILY_HARD_LIMIT` and random hooks.

| Property | Type |
|---|---|
| `Rule Name` | Title |
| `Best Slots` | Text (JSON array) |
| `Best Content Types` | Text (JSON array) |
| `Best Hook Type` | Select (`A` / `B` / `C`) |
| `Daily Limit` | Number |
| `Updated At` | Date |
| `Notes` | Text |

> Note: the workspace also has a separate **Agent Rules** database (free-text
> rules: `Rule Content` / `Category` / `Confidence` / `Evidence Post IDs`). It is
> a different, narrative model and is **not** what Loop 1 reads. Reconciling the
> two is a future decision.

---

## Scheduling

### GitHub Actions (zero-cost, included)

- `.github/workflows/post.yml` — Loop 1 at the five HKT slots (cron is UTC; the
  job auto-detects the nearest HKT slot, so minor cron drift is harmless).
- `.github/workflows/learn.yml` — Loop 2 nightly.
- `.github/workflows/tests.yml` — runs the test suite on every PR.

Set repository **secrets**: `NOTION_TOKEN`, `X_API_KEY`, `X_API_SECRET`,
`X_ACCESS_TOKEN`, `X_ACCESS_SECRET`, `X_BEARER_TOKEN`. The non-secret Notion DB
IDs (including Posting Rules) are set inline in the workflows.

### VPS cron (alternative)

```cron
30 7,10,12,18,21 * * *  cd /opt/loop && .venv/bin/python main.py --loop 1 --yes
0  2              * * *  cd /opt/loop && .venv/bin/python main.py --loop 2
```

---

## Content rules (enforced / assisted)

1. One argument per draft.
2. Unified CTA: `完整框架＋案例在 Substack 👉 [URL]`.
3. Traditional Chinese written style.
4. ≤ 280 characters per tweet (over-length posts are flagged in the log).
5. No investment advice.
6. Framework first.

---

## Project layout

```
config/      settings.py (env) · schema.py (Notion property names)
core/        pure, dependency-free logic — models, selection, composition,
             analysis, parsing, timeutil (fully unit-tested)
services/    notion.py · twitter.py · claude.py (external I/O)
loops/       post_loop.py · learn_loop.py · generate_loop.py
prompts/     generate.txt (Loop 3 starter prompt)
utils/       logging_setup.py
tests/       pytest suite (no network required)
main.py      CLI entry point (--loop 1/2/3, --dry-run)
```

The `core/` package imports no SDKs and no secrets, so the logic that decides
*what to post* and *how to compose it* is tested without touching the network.

---

## Testing

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

---

## Status

- **Loop 1 — POST**: complete, tested, ready to run.
- **Loop 2 — LEARN**: complete; the Posting Rules DB now exists, so rule-writing
  is live (activates once ≥20 data points accumulate). Non-public X metrics
  (impressions, link clicks) require user-context auth on your own recent tweets.
- **Loop 3 — GENERATE**: complete; provide the article text via `--article-file`.

Secrets live only in `.env` / CI secrets and are never committed.
