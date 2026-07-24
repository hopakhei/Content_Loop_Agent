# LOOP Eval Upgrade Plan (P0 + P1)

**Status:** approved for implementation. This document is self-contained — it is
written for an implementing session that has NOT seen the design discussion.
Read the whole file before writing code.

**Goal:** upgrade Loop 2 (LEARN) from a single pooled engagement metric into a
per-platform, tag-driven experiment engine, and re-point the X objective from
funnel (link clicks) to **follower growth**. Four findings drive this:

1. Rules are learned pooled across platforms, but X and Threads audiences
   differ; X impressions and Threads views are not comparable denominators.
   The only rule that changes behaviour (Best Hook) mixes both platforms.
2. Experiment dimensions are too thin, and `Loop Version` (COMPOSITION_VERSION)
   is polluted: v3 was minted for "X link-free", then the bare-link CTA change
   and the GitHub-CTA change shipped WITHOUT bumping it, so v3 rows mix three
   different compositions. Era numbers are also time-confounded. Replace this
   mechanism with explicit per-row tags.
3. "Does dropping the Substack link on X improve engagement?" cannot be
   answered from historical data (confounded). It needs a randomized per-post
   A/B, tagged at post time.
4. The X account is in follower-growth mode, but the eval has zero observation
   of followers. Measure follower counts nightly and optimize X for a
   growth-proxy score instead of engagement-with-link-clicks.

---

## 0. Context primer (read first)

### Architecture map

```
config/settings.py     env config (X_INCLUDE_CTA, X_CTA_BY_ISSUE, budgets…)
config/schema.py       Notion property names (Drafts / Articles / Performance / AgentRules)
core/                  PURE logic, no SDK imports, fully unit-tested
  analysis.py          DataPoint + ranked()/best_*() aggregation
  composition.py       compose_posts, strip_cta, hooks, CTA handling
  selection.py         draft selection ladder
core/parsing.py        Loop 3 unit parsing + label maps
services/
  notion.py            NotionService (notion-client SDK, data_sources API)
  twitter.py           TwitterService (tweepy; get_metrics with user_auth=True)
  threads.py           ThreadsService (requests; publish retry; get_insights)
loops/
  post_loop.py         Loop 1 — platform-aware publish (per-platform hooks/CTA)
  learn_loop.py        Loop 2 — nightly refresh + rankings + write_rules
main.py                CLI (--loop 1/2/3, --check, --inspect-threads)
.github/workflows/     post.yml (5 slots/day), learn.yml (nightly 18:00 UTC),
                       generate.yml, edit.yml, check.yml, inspect.yml, tests.yml
tests/                 pytest, no network, fakes for services (92 passing)
```

### Operational facts the implementation MUST respect

- **The sandbox cannot reach api.notion.com / api.x.com / graph.threads.net**
  (proxy 403). All real-world validation happens on GitHub Actions runners.
  The Notion MCP connector is unreliable (frequent mid-write disconnects) —
  do NOT depend on it; use the repo's own services via workflows.
- **X credit budget:** every write AND read spends the same monthly allowance.
  Loop 2 reads each post exactly once (age 24–48h window, batched 100/request).
  Do not add re-reads. The follower snapshot below adds exactly +1 X read/day.
- **X is currently parked** (402 quota exhaustion, `X Parked Until` rule in
  Agent Rules; auto-resumes ~Aug 1). X-side changes will not produce data
  until then — they must ship dormant-safe.
- Loop 1 currently posts per platform with: per-platform hook variants
  (`_pick_hooks_per_platform`), per-platform CTA (`_x_cta_for`, GitHub for
  issue 201 via `settings.X_CTA_BY_ISSUE`), X chain cap
  (`X_MAX_THREAD_POSTS=1`), bare-link CTA (no sell copy).
- Performance rows are created once per platform per posting event
  (`NotionService.create_performance_record`), keyed by root post id.
- The `Performance` DB has an unused **`AI Notes`** rich-text property
  (`Performance.AI_NOTES`) — use it for the tags JSON. Do NOT add new Notion
  schema properties in this work.
- Tests must stay network-free; extend the existing fakes.

---

## 1. P0-W1 — Machine tags on every Performance row

**Why:** one generic tagging mechanism replaces era-versioning and makes every
future A/B a one-line change.

### 1.1 Write side (Loop 1)

In `loops/post_loop.py::_publish_one`, build a tags dict per platform at
publish time and pass it to `create_performance_record`:

```python
tags = {
    "platform": platform,                  # "X" / "Threads"
    "hook": hook_for[platform][0],         # "A"/"B"/"C" or None
    "has_link": plat_cta is not None and any(plat_cta in p for p in posts_for[platform]),
    "link_domain": _domain(plat_cta) if has_link else None,   # "substack.com"/"github.com"
    "chain_len": len(posts_for[platform]),
    "series": _series_of(draft),           # "1xx" analysis / "2xx" build-in-public, from title #NNN-
    "len_bucket": _len_bucket(posts_for[platform][0]),  # "short" <=140 / "mid" <=280 / "long"
    "comp": 4,                             # static int, bump ONLY on composition logic changes
}
```

Helpers are pure — put `_domain`, `_series_of`, `_len_bucket` in
`core/composition.py` or a new `core/tagging.py` (preferred; keep it pure and
unit-tested). `link_domain` = registrable domain of the URL host, enough to
distinguish `substack.com` vs `github.com`; naive parse
(`urlparse(url).hostname` → last two labels) is fine.

`services/notion.py::create_performance_record` gains `tags: Optional[dict]`;
when present, serialize compact JSON (`json.dumps(..., ensure_ascii=False)`)
into `Performance.AI_NOTES`.

Keep writing `loop_version` for backwards compatibility but freeze it at the
current constant; tags are the source of truth going forward.

### 1.2 Read side (Loop 2)

`services/notion.py::get_performance_rows` parses `AI Notes` as JSON into
`row["tags"]` (empty dict on parse failure/blank — old rows have none).

`core/analysis.py::DataPoint` gains `tags: dict = field(default_factory=dict)`.
`loops/learn_loop.py::_to_point` copies them, falling back for old rows:
`tags.setdefault("platform", row platform)`, `tags.setdefault("hook", …)`.

### 1.3 Tag rankings

Add to `core/analysis.py`:

```python
def ranked_by_tag(points, tag: str, min_n: int = 1, platform: str | None = None):
    """(tag_value, avg_rate, n) ranking; optionally restricted to one platform.
    Points MISSING the tag are excluded (unknown ≠ False)."""
```

LEARN logs, per platform: `has_link`, `link_domain`, `chain_len`, `series`,
`len_bucket` rankings (only when the tag has ≥2 distinct values present).
These are informational lines + go into the LEARN Summary rule text.

**Edge cases:** rows without tags are excluded from tag rankings (do not
treat missing as false); malformed JSON in AI Notes must not crash LEARN.

---

## 2. P0-W2 — Per-platform Best Hook (learn it AND act on it)

### 2.1 Schema (`config/schema.py::AgentRules`)

```python
RULE_BEST_HOOK_X = "Best Hook (X)"
RULE_BEST_HOOK_THREADS = "Best Hook (Threads)"
```

Keep the old pooled `RULE_BEST_HOOK` write for continuity but Loop 1 stops
using it when a platform-specific rule exists.

### 2.2 LEARN write (`loops/learn_loop.py`)

For each platform with points: `best_hook(platform_points, min_n=MIN_CELL_N)`
(see W3). Write the platform rule only when a winner exists at that min_n;
otherwise skip (leave any previous rule row as-is — do not deprecate
automatically).

### 2.3 Rules model + read (`core/models.py::Rules`, `services/notion.py::get_rules`)

`Rules` gains `best_hook_by_platform: dict[str, str]` (default `{}`). Parser
maps the two new rule titles into it (same "first char A/B/C" normalization as
the pooled rule).

### 2.4 Loop 1 consumption (`loops/post_loop.py::_pick_hooks_per_platform` + `core/composition.py::select_hook`)

`select_hook` gains an optional `winner_override: Optional[str]` param (or an
equivalent mechanism) so the caller can bias per platform:

- X pick: weighted toward `best_hook_by_platform.get("X")`, falling back to
  the pooled `best_hook_type`, else random.
- Threads pick: weighted toward `best_hook_by_platform.get("Threads")`, same
  fallback chain.
- Preserve the cross-platform exploration property: on a dual-platform draft,
  if both platforms independently pick the SAME variant and ≥2 variants exist,
  shift Threads to the next variant in cyclic order (existing behaviour).

Existing tests to update: `test_loop1_dual_platform_uses_different_hooks`
(behaviour preserved), plus new tests: platform winners honored; same-pick
divergence still enforced.

---

## 3. P0-W3 — Minimum cell size before a rule is written

`MIN_CELL_N = 8` (module constant in `learn_loop.py`).

- Rule-writing paths (`best_hook` per platform, `best_slots`,
  `best_content_types`) pass `min_n=MIN_CELL_N`. A cell below 8 points cannot
  produce a written winner (today `min_n=1`: 3 posts can set the global hook).
- Informational log rankings keep `min_n=1` — visibility is fine, action isn't.
- The overall `MIN_DATA_POINTS = 20` gate stays.

---

## 4. P0-W4 — Nightly follower snapshots (both platforms)

### 4.1 Collection (in LEARN, before metric refresh; NOT in Loop 1)

- **X:** `TwitterService.get_follower_count()` →
  `client.get_me(user_fields=["public_metrics"], user_auth=True)` →
  `public_metrics["followers_count"]`. Costs 1 read/day — acceptable. On any
  exception, log a warning and skip (never fail the run). Skip entirely while
  X is parked? NO — reads are not blocked by the write cap; still attempt it,
  but degrade on 429/402 silently.
- **Threads:** `ThreadsService.get_follower_count()` →
  `GET {API_BASE}/{user_id}/threads_insights?metric=followers_count&access_token=…`
  (requires the `threads_manage_insights` token scope; if the call errors,
  log the existing scope hint once and skip).

### 4.2 Storage — one Agent Rules row per platform

Rule title `Follower History (X)` / `Follower History (Threads)`
(add constants to `AgentRules`). `Rule Content` = compact JSON object of the
most recent 90 entries: `{"2026-07-13": 123, …}` (HKT dates). Upsert via the
existing `_upsert_rule` (category `Meta`, confidence 100, no evidence). Trim
to 90 keys on every write. Loop 1 ignores these rows (unknown titles are
already ignored — verify `get_rules` doesn't trip on them).

### 4.3 Reporting

LEARN logs and includes in the summary dict:
`follower deltas: X +12 (7d), Threads +45 (7d)` — computed from the history
JSON. Add the line to the LEARN Summary rule text so it's visible in Notion.

---

## 5. P1-W5 — Randomized X link A/B (answers the Substack question properly)

**Design:** while `X_LINK_AB=true` (new `_flag`, default **true**), each X
posting event flips a fair coin:

- arm `link`: X variant composed exactly as today (bare link; per-issue GitHub
  override still applies).
- arm `no_link`: X variant passed through `strip_cta` (link-free), regardless
  of `X_INCLUDE_CTA`.

Record `"x_link_arm": "link" | "no_link"` in the W1 tags (X row only).
Randomness: `random.random() < 0.5` at publish time is fine (no seeding
requirement); in `--dry-run` still pick an arm so previews are honest.

Interaction rules:
- `X_INCLUDE_CTA=false` disables the A/B (everything is no_link, no arm tag —
  or tag all as no_link; pick one and test it).
- Thread cap and hook logic unchanged.
- Dormant-safe: while X is parked nothing posts, so the experiment simply
  begins when X auto-resumes (~Aug 1). No special handling needed.

**Analysis:** LEARN reports, X-only: mean engagement rate + n per arm (uses the
W1 tag ranking with `platform="X"`, tag `x_link_arm`). Add a stopping note in
the LEARN Summary once each arm has n≥30: name the leading arm and the gap in
% terms. Do NOT auto-flip `X_INCLUDE_CTA` — surface the answer, the human
decides (matches the system's "rules change behaviour only where explicit"
philosophy).

---

## 6. P1-W6 — X growth objective (followers over funnel)

### 6.1 Extra signals, zero extra reads

`TwitterService.get_metrics` already batch-reads each post once. Extend the
same request:

- `public_metrics` now also carries `bookmark_count` — capture it.
- Request `organic_metrics` in addition to `non_public_metrics`
  (`tweet_fields=["public_metrics","non_public_metrics","organic_metrics"]`);
  `organic_metrics.user_profile_clicks` is the strongest follow proxy.
  Availability on the free tier is unverified: if the request is rejected,
  fall back exactly like the existing non_public fallback (strip the field,
  retry once), and treat the metric as absent.

Persistence without schema changes: merge `{"bookmarks": n, "quotes": n,
"profile_clicks": n}` into the row's AI Notes tags JSON during
`update_performance_metrics` (read-modify-write of the tags dict —
`NotionService` must merge, not overwrite, the existing tags). Numeric columns
(Impressions/Likes/Replies/Reposts/Link Clicks) unchanged.

### 6.2 Growth score (pure function, `core/analysis.py`)

```python
def growth_score(p: DataPoint) -> Optional[float]:
    """Follower-growth proxy per impression, X posts only.
    (3*replies + 2*reposts + 2*bookmarks + 1*quotes + 4*profile_clicks) / impressions
    Missing signals count as 0; None when impressions unavailable."""
```

Weights are a starting prior (conversation and profile visits drive follows;
bookmarks signal reference value) — put them in module constants so they're
tunable.

### 6.3 Objective per platform in LEARN

- `Best Hook (X)` is computed on **growth_score** ranking (min_n from W3).
- `Best Hook (Threads)` stays on engagement rate.
- Log both metrics for X ("Engagement · X" and "Growth · X") so the divergence
  itself is visible.
- LEARN Summary includes the 7-day follower delta next to the growth ranking.

---

## 7. Explicitly OUT of scope

- No selection-ladder changes (platform-specific content-type preference is P2).
- No hook sentence-pattern capture at generate time (P2).
- No new Notion DB properties, no Notion MCP usage, no auto-flipping of
  X_INCLUDE_CTA, no extra X API reads beyond +1/day (follower count), no
  change to the read-once 24–48h window, no re-reads of old posts.
- Do not modify the X park/unpark, failure-notice, or quota-telemetry logic
  except where explicitly stated above.

---

## 8. Delivery plan (suggested commits)

1. **Tags foundation (W1):** core/tagging.py + DataPoint.tags +
   create_performance_record(tags=…) + get_performance_rows parsing +
   ranked_by_tag + LEARN tag logging. Tests: tag construction (domain/series/
   len_bucket edges), JSON round-trip via fakes, malformed-JSON tolerance,
   missing-tag exclusion.
2. **Per-platform hooks + min_n (W2+W3):** schema consts, Rules model, get_rules
   parsing, learn writes, select_hook override, post_loop per-platform bias.
   Tests: winner-per-platform honored; divergence preserved; no rule written
   below MIN_CELL_N.
3. **Follower snapshots (W4):** two service methods + LEARN collection/storage/
   delta reporting. Tests: history trim to 90, delta math, graceful skip on
   errors (fakes raising).
4. **Link A/B (W5):** flag, arm flip, tag, LEARN arm report. Tests: both arms
   produce correct composition; arm recorded in tags; X_INCLUDE_CTA=false
   behaviour; dry-run previews an arm.
5. **Growth objective (W6):** metrics capture (incl. fallback chain), tag-merge
   on update, growth_score, Best Hook (X) on growth. Tests: score math with
   missing signals, organic_metrics fallback, tag merge preserves post-time tags.

Each commit: full `python -m pytest -q` green (baseline 92 tests — do not break
them; several assert exact preview/CTA behaviour and will need updating only
where this plan changes behaviour). Update README (§Loop 2, §composition) and
`.env.example` (X_LINK_AB) in the commit that introduces each change.

### Acceptance checklist

- [ ] Every new Performance row carries a tags JSON in AI Notes; LEARN parses
      it and prints per-platform tag rankings without crashing on legacy rows.
- [ ] Agent Rules contains `Best Hook (X)` / `Best Hook (Threads)` only when
      their cells reach n≥8; Loop 1 biases each platform by its own winner.
- [ ] `Follower History (X/Threads)` rows update nightly; LEARN summary shows
      7-day deltas.
- [ ] With X unparked, X posts alternate randomly between link/no_link arms and
      the arm is visible in the row tags; LEARN reports per-arm engagement.
- [ ] Best Hook (X) is driven by growth_score; bookmarks/profile-clicks appear
      in tags when the API grants them; all failures degrade to warnings.
- [ ] `python -m pytest -q` green; no test touches the network.

### Post-merge validation (on GitHub Actions, not locally)

1. Dispatch `learn.yml` once — confirm snapshot rows + tag rankings appear and
   the run is green (it will refresh only in-window posts; that's fine).
2. Wait for the next scheduled Threads post — confirm its Performance row has
   the tags JSON.
3. After Aug 1 (X unpark) — confirm the first X posts carry `x_link_arm` and
   the arm distribution is roughly balanced over a week.
