---
id: H-004
status: open
source: own-metrics
created: 2026-07-29
claim: >
  The framework series reaches an order of magnitude more people on Threads than
  the numbered-essay series it replaced.
variable:
  key: series_era
  scorer: series_era
  arms: [framework, numbered]
prediction:
  metric: impressions
  platform: Threads
  direction: framework > numbered
  min_effect: 2.0
  n_per_arm: 7
  stop_by: 2026-09-30
confounds:
  - >
    Not one variable. The framework era changed the subject matter, the chain
    length (1 to 7 posts), the attribution, and the composition version, all on
    the same day. This card measures the bundle and says so.
  - >
    Strictly a before/after with no concurrent control, which is the weakest
    design there is. Kept anyway because the effect is far larger than anything
    else in the corpus and because it recalibrates what a "big" effect means here.
---

# H-004 — the size of the thing nobody logged

## Why this card exists

The nightly digest ranks slots, content types and hooks. It never reported that
on 2026-07-23 mean Threads impressions went from roughly 640 to roughly 5,300.
That single change is larger than every effect the digest has ever ranked, put
together.

It went unreported because the digest's headline metric is engagement *rate*,
and the rate moved much less than reach did — a bigger audience is a colder
audience, so a tenfold gain in impressions shows up as roughly a doubling in
rate. Ranking by rate can prefer the smaller audience.

## What this card is for

Not for deciding anything — the direction is not in doubt and the series is
already the strategy. It exists to set the scale. A hypothesis predicting a 1.2x
effect is not worth six weeks of posting slots on an account where the available
effects are this large, and this card is the reference that says so.

## The open question underneath

Which part of the bundle did it? Subject matter, chain length, or provenance.
H-001 takes the first slice.

## Retro result — 2026-07-29 — retro-supports, 9.27x

`framework` n=7 (mean 5,939 impressions), `numbered` n=41 (mean 641), ratio
9.27x, 90% CI [4.21, 15.75]. Both confound checks fired, correctly: the arms do
not overlap in time at all, and each sits entirely in one content era.

Read it as a scale marker, not a causal claim. The largest effect anyone has
proposed testing on this account is 1.5x; the bundle that actually moved is 9x.
Ranking hooks and slots against each other is rearranging something an order of
magnitude smaller than the thing nobody logged.
