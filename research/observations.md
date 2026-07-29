# Observations

Append-only. Raw notes go here; hypotheses go in `hypotheses/`. Never edit or
delete an entry — a log that gets tidied up stops being evidence of what was
believed when.

**An observation is not a result.** Anything from outside this account — a
reader's reply, another account's numbers, a published study — can start a
hypothesis and can never close one. Those are measurements of somebody else's
audience. The only thing that closes a card is a randomised run on ours.

Format: `## YYYY-MM-DD — one line` / source / what was seen / what it might mean.

---

## 2026-07-29 — Threads reach changed by ~9x when the framework series started

- **source**: own-metrics (Notion Post Performance, 55 Threads rows)
- **seen**: mean impressions 641 for the numbered essays (n=41, 07-06..07-23),
  5,939 for the framework series (n=7, 07-23..07-28). Engagements 1.5 → 24.
- **means**: the largest movement in the account's history, and the nightly
  digest never mentioned it. Four things changed the same day, so this is one
  observation about a bundle, not four about variables. → H-004

## 2026-07-29 — the digest reports a winner without ever reporting n

- **source**: own-metrics (`state/performance_digest.md`)
- **seen**: `Best Hook by platform → X=C, Threads=A`, with no sample size and no
  gap between first and second. `core.analysis.best_hook` returns `rows[0][0]`.
- **means**: a 3x lead and a 0.02% lead are printed identically, and the
  downstream auto-producer cannot tell them apart.

## 2026-07-29 — the confidence number was hard-wired to zero

- **source**: own-metrics (code read)
- **seen**: `_write_digest` runs before `confidence` is assigned to the summary
  dict, so `summary.get("confidence", 0)` always took the default. Every digest
  ever written reported 0%, at 151 data points against a threshold of 40.
- **means**: the one number in the pipeline that expresses uncertainty was
  broken for weeks and nobody noticed, because no decision consumed it. Fixed.

## 2026-07-29 — the X link experiment stopped randomising and kept reporting

- **source**: own-metrics (Notion, `x_link_arm` tag)
- **seen**: the `link` arm has no rows after 2026-07-19; `no_link` continues to
  07-28. Arm assignment is gated on `X_INCLUDE_CTA`, which was switched off.
- **means**: since then every X post has been `no_link` by construction rather
  than by coin flip, while the digest kept printing the two as a live
  comparison — and the gap kept growing for an unrelated reason (X reach rose
  4x when the framework series launched). → H-003

## 2026-07-29 — the authority rule was written from text that had not shipped yet

- **source**: own-metrics (git history vs Notion drafts)
- **seen**: `units/*.md` were rewritten on 2026-07-25 to lead with provenance.
  Most framework posts went out before that. Scoring the working-tree files put
  bcg-matrix in the "has provenance in line 1" arm; the version that actually
  shipped opened `一間正在賺錢的公司，可能已經在死。` with no name in line 1.
- **means**: BCG (19,115) and Bowman (1,540) are *identical* on provenance
  position — both carry it in the second paragraph. The 12x gap between them,
  which is what the rule in the x-post skill was derived from, is not explained
  by the variable the rule is about. → H-001, and the skill rule needs revisiting.

## 2026-07-29 — enforcing a rule in CI destroyed the data needed to test it

- **source**: own-metrics
- **seen**: `test_every_framework_hook_carries_an_authority_signal` requires
  every unit's Hook A to name a firm or an author. It was added before the
  hypothesis was written down. All twelve units now comply, so the negative arm
  no longer exists.
- **means**: a rule adopted from a hunch and then enforced stops looking like a
  hunch, because counter-examples become impossible to produce. Any live test of
  H-001 needs that check relaxed to admit a documented experimental arm.

## 2026-07-29 — IG comment text is fetched daily and thrown away

- **source**: own-metrics (`loops/dm_loop.py`)
- **seen**: the DM loop reads every comment on recent media, keyword-matches it,
  and stores only the comment id for idempotency. The body is discarded.
- **means**: the richest available source of hypotheses — readers describing in
  their own words what they wanted — is being collected and dropped every day.
