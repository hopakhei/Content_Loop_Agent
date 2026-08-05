---
id: H-003
status: abandoned
source: own-metrics
created: 2026-07-29
closed: 2026-07-29
claim: >
  On X, a post carrying an outbound link reaches fewer people than the same post
  without one.
variable:
  key: x_link_arm
  scorer: x_link_arm
  arms: [no_link, link]
prediction:
  metric: impressions
  platform: X
  direction: no_link > link
  min_effect: 1.5
  n_per_arm: 15
  stop_by: 2026-09-30
confounds:
  - >
    The `link` arm stopped being assigned on 2026-07-19 when X_INCLUDE_CTA was
    turned off; `no_link` kept accruing rows through the framework-series launch,
    when X impressions rose from a mean near 40 to near 178. The two arms are
    therefore partly a before/after comparison of the account itself.
---

# H-003 — what a link costs on X

## Status of the existing experiment

This is the only variable the pipeline ever actually randomised
(`X_LINK_AB` in `config/settings.py`). It stopped randomising on 2026-07-19,
because the arm assignment is gated on `X_INCLUDE_CTA`, which was switched off.

Nothing recorded that. The nightly digest kept printing

    X link A/B (engagement) → no_link: 0.65% (n=28); link: 0.00% (n=15)

as though both arms were still live, and the gap kept widening for a reason that
has nothing to do with links: every row added to `no_link` after 07-19 came from
a period when the account's reach on X had changed by a factor of four.

An experiment that ends silently is worse than one that was never run, because
its output keeps being read.

## What the randomised window says

Restrict to 2026-07-13..07-19, when both arms were being assigned, and see
`research/retro_report.md`. The direction there is not the one the digest
reports.

## Prior from outside

Buffer's 18.8M-post analysis is where the original 30-50% reach penalty came
from. That is a hypothesis source, not evidence about this account: different
followers, different niche, different account size. It cannot close this card.

## Retro result — 2026-07-29 — inconclusive, and the reported direction reverses

`no_link` n=24 (mean 43.9 impressions), `link` n=15 (mean 37.9), ratio 1.16x,
90% CI [0.71, 2.01]. The confound check fired on its own: the arms share only
43% of their span.

The digest has been reporting `no_link: 0.65% (n=28); link: 0.00% (n=15)` — a
total wipeout. On impressions, within the window where both arms were actually
being assigned, there is no detectable difference at all. The engagement-rate
version of the comparison is close to meaningless here: X likes are 0 on all but
two rows in the entire corpus, so that rate is mostly measuring whether a single
reply happened.

Nothing here justifies keeping links off X, and nothing here justifies putting
them back. The honest state is: unmeasured. Either restart the randomisation
with a stopping rule, or close the card as abandoned and stop citing its numbers.

## Closed — 2026-07-29 — abandoned, not refuted

Abandoned means we stopped asking, not that we answered. The direction is still
unknown; nothing below claims otherwise.

**Why not just restart the randomisation.** One experiment runs at a time, and
H-002 is worth more. This one affects whether a CTA appears; H-002 affects the
opening line of every post on the platform that carries this account's reach.

**Why the answer barely matters right now.** X averaged 178 impressions per post
in the framework era against 5,939 on Threads. A 30% swing either way on X is
about 50 impressions — under 1% of what one Threads post does. Substack traffic
comes from Threads and the Instagram DM reply, not from X. Spending six weeks of
the single experiment slot to resolve a rounding error is the wrong trade.

**What happens now.** X stays link-free, which is already the state
(`X_INCLUDE_CTA=False`) — kept as a default, not as a finding. `X_LINK_AB` stays
switched on so that turning the CTA back on resumes randomising rather than
silently producing a single-arm stream.

**Reopen when** X sustains more than roughly 500 impressions per post, or the
account starts driving subscriptions through X. Then the question is worth a slot.

**Fixed so this cannot recur.** `loops/learn_loop.py` now refuses to print an arm
comparison when one arm has not been assigned for `STALE_ARM_DAYS`; it prints
`STALE, not reported` with the date instead. `scripts/retro_test.py` flags
non-concurrent arms independently. The failure was never the experiment ending —
experiments end. It was that nothing noticed, and the output kept being read.
