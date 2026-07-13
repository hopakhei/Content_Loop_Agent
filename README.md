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
Instagram          金句 → 圖卡 → 發佈              (cron, 1×/day 12:30 HKT)
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

1. Reads the daily quota from the **Agent Rules** (falls back to `DAILY_HARD_LIMIT`).
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

**Platforms:** each draft is published to every platform its `Platform`
multi-select names — X always, **Threads** when `THREADS_ACCESS_TOKEN` is set.
A dual-platform draft creates one Post Performance row per platform but counts
as **one** posting event toward the daily limit. Without a Threads token the
system behaves as X-only and Threads-only drafts (故事貼, 金句裂變) are skipped.

**X credit budget:** every X API call — each tweet in a chain, and each
metrics read — spends the same monthly credit allowance, so the system is
tuned to run inside the Free tier:

- X posts are link-free single tweets (`X_INCLUDE_CTA=false`) and chains are
  capped at the root tweet (`X_MAX_THREAD_POSTS=1`); the full thread + CTA
  still posts on **Threads, whose API is free**.
- Loop 2 reads each post's metrics **exactly once** (age 24–48h, batched
  100/request) and logs estimated writes used vs `X_MONTHLY_WRITE_BUDGET`
  (default 500), warning at 80%.
- `--check` skips the X credential read unless `--with-x` is passed.
- On a **402** (monthly cap exhausted) Loop 1 writes an `X Parked Until` rule
  into Agent Rules and posts **Threads-only** until the 1st of the next month
  — no wasted attempts, no repeated alerts. Deprecate/delete that rule in
  Notion to resume earlier (e.g. after upgrading the API tier).

To enable Threads: create a Meta app at developers.facebook.com with the
*Threads API* use case, add your account as a Threads tester (accept the invite
in the Threads app under Settings → Account → Website permissions → Invites),
generate a long-lived user token with `threads_basic` +
`threads_content_publish` + `threads_manage_insights` (the last one lets
Loop 2 read views/likes for Threads posts), and set the `THREADS_ACCESS_TOKEN`
secret (`THREADS_USER_ID` optional — auto-resolved). Tokens last ~60 days;
refresh via `GET /refresh_access_token`.

## Instagram — Quote Cards (detail)

Instagram is a **separate low-cadence image loop**, not part of the 5×/day
text loop — IG posts are image-only and the Graph API needs the picture at a
public URL. Once a day (`instagram.yml`, 12:30 HKT) the loop:

1. Picks the next `Quote Card` draft (`Content Type = Quote Card`) that has no
   Instagram Performance row yet, lowest `Argument #` first.
2. Renders the quote onto a branded 1080×1350 PNG (`services/imagecard.py`,
   Pillow-only, CJK font from `IG_FONT_PATH` → local asset → system
   `fonts-noto-cjk`). The card text is the Post Body minus its CTA/link line.
3. **Commits the PNG** into `cards/` so `raw.githubusercontent.com` serves it
   as the public `image_url`.
4. Publishes via the two-step Graph flow (create media container → poll until
   `FINISHED` → publish). The caption = hook + quote + a bio-CTA line +
   hashtags (IG rewards hashtags; caption links aren't clickable, so the
   Substack link lives in the bio).
5. Writes an `Instagram` Performance row (tagged like every other platform, so
   Loop 2 can rank hooks for IG separately).

```bash
python main.py --instagram --dry-run   # render + preview the card, no publish
python main.py --instagram             # render, then publish (needs IG token)
```

To enable Instagram: switch the IG account to **Professional**, add the
**Instagram** product to the same Meta app used for Threads, generate a token
with `instagram_business_basic` + `instagram_business_content_publish`, and set
the `IG_ACCESS_TOKEN` secret (`IG_USER_ID` optional — auto-resolved). The
workflow sets `IG_CARD_URL_BASE` from the repo + branch automatically. Until
the token is set, the workflow renders + previews but skips the publish.

### Composition model

`Post Body` is the canonical content. The three `Hook` fields are *alternative
opening lines* used by the A/B/C experiment.

- **Hook**: Loop 1 picks one hook variant (weighted toward the winning hook from
  the Agent Rules, else random among the non-empty hooks) and prepends it to the
  first post/tweet. If no hook fields have text, the body is posted as-is.
- **CTA**: effective URL = draft override → else Article CTA URL. The CTA is a
  **bare link** — just the URL on its own line, no "完整框架＋案例在 Substack 👉"
  sell copy and no "click here" gesture.
  - A CTA placeholder in the body — `{CTA_URL}` or the human `[連結]` (also
    `[link]`/`[CTA]`) — is substituted with the URL; if no CTA is present the
    bare link is appended (a new final tweet for threads).
  - Older drafts baked the salesy `完整框架…👉 URL` line into their body; that
    line is **softened to the bare link at compose time**, so no draft rewrite
    is needed.
  - **X carries the link by default** (`X_INCLUDE_CTA=true`). Set it `false` to
    post X link-free (max reach, no link suppression, no write-quota CTA cost)
    while growing followers — **Threads keeps the link regardless.** Rows are
    stamped `Loop Version` so Loop 2 can compare composition eras.
- **Threads**: a `Thread` body is split into tweets **only** on an explicit
  separator line — 3+ dashes/em-dashes (`---` or `———`). Blank lines inside a
  tweet are preserved; a body with no separator posts as a single tweet. (We do
  not split on blank lines — that over-fragments the thread.)

---

## Loop 2 — LEARN (detail)

Nightly (02:00 HKT). Refreshes engagement metrics **per platform** — X post ids
go to the X API (user-context auth; impressions/link clicks are
`non_public_metrics`, plus `bookmark_count` and `organic_metrics.user_profile_clicks`
as follower-growth proxies when the tier grants them), Threads post ids go to
the Threads Insights API (`views` → Impressions; needs the
`threads_manage_insights` scope), and Instagram media ids go to the IG Insights
API (`views`/`reach` → Impressions, `comments` → replies, `shares` → reposts,
`saved` → bookmarks and `profile_visits` → profile clicks as growth proxies;
metric set degrades gracefully across API versions). Each post is read **exactly
once**, in the 24h–48h age window (never re-read — reads spend the same monthly
credit as writes).

**Tag-driven, per-platform experiments.** Every Performance row carries a
machine-tag JSON in its `AI Notes` property (`core.tagging`): platform, hook,
`has_link`, `link_domain`, `chain_len`, `series` (1xx/2xx), `len_bucket`,
`x_link_arm`. Loop 2 ranks any tag, **within each platform separately** (X
impressions, Threads views and IG views are not comparable). A cell must reach
**≥8 points** before it can set a written rule (guards against a 3-post fluke).

**Per-platform objectives.** X is in follower-growth mode, so `Best Hook (X)`
is learned on a **growth proxy** (`3·replies + 2·reposts + 2·bookmarks +
1·quotes + 4·profile_clicks` per impression); `Best Hook (Threads)` and
`Best Hook (Instagram)` stay on engagement rate. Each posting flow biases toward
its own platform's winner (Loop 1 for X/Threads, the Instagram loop for IG),
falling back to the pooled `Best Hook`; Loop 1 still shifts Threads to a
different variant when both platforms pick the same one, so exploration
continues.

**Follower telemetry.** Each night LEARN snapshots every configured platform's
follower count into `Follower History (X/Threads/Instagram)` rules (90-day JSON)
and reports the 7-day delta.

**X link A/B.** With `X_LINK_AB` on, each X post is randomly assigned to a
`link` or `no_link` arm (tagged), so "does dropping the Substack link help?" is
answered by a clean randomized test rather than a confounded before/after. LEARN
reports engagement per arm; it never auto-flips `X_INCLUDE_CTA` — you decide.

With ≥20 usable points it writes the winners into **Agent Rules** as `Active`
rows (with `Confidence` + `Evidence Post IDs`) that Loop 1 reads next run.

> Note: metrics are blank until a post crosses 24h **and** the next nightly LEARN
> picks it up — expect the first numbers the second night after posting. If X
> rejects the richer metric fields, LEARN degrades through non-public → public
> counts instead of failing.
>
> The implementation follows `docs/eval-upgrade-plan.md`.

---

## Loop 3 — GENERATE (detail)

Manual, per article. Two ways to produce the 12 units — generation and Notion
insertion are decoupled:

- **Claude API path** (`--article-file articles/<issue>.md`): sends the article
  through `prompts/generate.txt` via the Anthropic API (`ANTHROPIC_API_KEY`,
  default model `claude-opus-4-8`, override with `CLAUDE_MODEL`). This is the
  only place in the whole system that spends API credits.
- **Pre-generated units path** (`--units-file units/<issue>.md`) — *zero API
  cost*: any Claude Code session (billed to the subscription, not the API key)
  writes the units in the generate.txt output format to `units/<issue>.md`;
  Loop 3 then just parses and inserts. The generate.yml workflow auto-detects
  `units/<issue>.md` and takes this path without needing `ANTHROPIC_API_KEY`.

Either way the units are parsed, their labels mapped to the Notion
select/multi-select options, and inserted into **Content Drafts** (Status =
`Draft`, Generation = 1) related to the Article.

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
| Posting Rules DB (spec) | Consolidated onto the existing **Agent Rules** DB (`4acdaa17-…`); the spec's separate Posting Rules DB is retired. |

### Agent Rules database — the single rules model

The system's "living rules" are stored in one database, **Agent Rules** (under
*90s.pm.investing — Content Hub*, data-source `4acdaa17-0e02-4aa6-988a-06927c905b96`,
baked into `.env.example` + the workflows). It holds two kinds of rows:

- **Operational rows** that Loop 1 mechanically reads. Loop 2 upserts them as
  `Active` rows, keyed by `Rule Title`, with the machine value in `Rule Content`:

  | `Rule Title` | `Category` | `Rule Content` | Used by Loop 1 |
  |---|---|---|---|
  | `Daily Limit` | Meta | integer | daily quota |
  | `Best Hook` | Hook | `A` / `B` / `C` | hook bias |
  | `Best Slots` | Timing | JSON array | informational |
  | `Best Content Types` | Structure | JSON array | informational |
  | `LEARN Summary` | Meta | prose | informational |

- **Narrative rows** (any other title) — human-readable insights/failures with
  `Confidence`, `Evidence Post IDs`, `Status` (Active/Testing/Deprecated),
  `Loop`, `Version`. Loop 1 ignores these.

Loop 1 reads only `Active` operational rows and parses `Rule Content`; if the DB
is unset/empty it falls back to `DAILY_HARD_LIMIT` and random hooks. Loop 2 stamps
each write with a `Confidence` (scaled by data-point count), the supporting
`Evidence Post IDs`, the `Loop` iteration, and a bumped `Version`.

---

## Scheduling

### GitHub Actions (zero-cost, included)

- `.github/workflows/post.yml` — Loop 1 at the five HKT slots (cron is UTC; the
  job auto-detects the nearest HKT slot, so minor cron drift is harmless).
- `.github/workflows/learn.yml` — Loop 2 nightly.
- `.github/workflows/tests.yml` — runs the test suite on every PR.

Set repository **secrets**: `NOTION_TOKEN`, `X_API_KEY`, `X_API_SECRET`,
`X_ACCESS_TOKEN`, `X_ACCESS_SECRET`, `X_BEARER_TOKEN`, and (optional, enables
Threads) `THREADS_ACCESS_TOKEN` + `THREADS_USER_ID`. The non-secret Notion DB
IDs (including Agent Rules) are set inline in the workflows. Until these secrets
exist, the scheduled `post`/`learn` runs **skip cleanly** (exit 0 with a notice)
rather than failing.

### Failure notices (closed loop)

A platform failure during POST (or any LEARN crash) makes the workflow run
**fail**, which does two things:

1. GitHub emails you (Settings → Notifications → Actions, on by default for
   failed runs you triggered/own).
2. The job files an alert into a rolling GitHub Issue labelled `loop-alert`
   (one comment per incident, with the run link and probable causes). Close
   the issue once fixed — the next failure opens a fresh one.

`skipped` outcomes (daily limit reached, no eligible draft) are not failures;
only real platform errors (X 403, Threads 4xx/5xx, partial threads) alert.

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
- **Loop 2 — LEARN**: complete; writes into the **Agent Rules** DB, so rule-writing
  is live (activates once ≥20 data points accumulate). Non-public X metrics
  (impressions, link clicks) require user-context auth on your own recent tweets.
  Threads metrics come from the Insights API and require the
  `threads_manage_insights` token scope.
- **Loop 3 — GENERATE**: complete; provide the article text via `--article-file`.

Secrets live only in `.env` / CI secrets and are never committed.
