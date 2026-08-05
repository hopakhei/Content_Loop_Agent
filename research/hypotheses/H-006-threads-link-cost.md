---
id: H-006
status: open
source: own-metrics
created: 2026-08-03
claim: >
  On Threads, a post without the Substack CTA link reaches more people than the
  same post carrying it.
variable:
  key: threads_link_arm
  scorer: threads_link_arm
  arms: [no_link, link]
prediction:
  metric: impressions
  platform: Threads
  direction: no_link > link
  min_effect: 1.3
  n_per_arm: 15
  stop_by: 2026-11-30
confounds:
  - >
    Runs alongside H-002, which is randomising the opening line on the same
    platform. The two coins are independent, so neither biases the other, but a
    link effect sits inside H-002's cells as extra variance and makes its
    interval wider than it would have been. Accepted deliberately: the
    alternative on the table was taking every Threads post link-free at once,
    which would have changed the composition of both H-002 arms mid-run.
  - >
    The CTA link is the only route from a Threads post to the article. If
    no_link wins on impressions it may still lose on the thing reach is for —
    check click-throughs and Substack signups over the same window before
    acting on an impressions result.
---

# H-006 — what the link costs on Threads

## Why this is a coin and not a switch

The question came in as "pull the link off Threads and see if reach goes up".
Doing exactly that produces a number, and the number is uninterpretable. This
account has already run that experiment once: H-003 pulled links off X, and the
comparison ended up measuring the eleven weeks between the two arms rather than
the link. X impressions moved from a mean near 40 to a mean near 178 in that
window for reasons that had nothing to do with links, and the digest went on
printing the two arms side by side as though they were comparable.

Threads is where this account's reach actually lives — 5,939 impressions per
post against 178 on X in the framework era — so the same mistake costs more
here. A fair coin per post puts both arms in the same weeks, against the same
follower count, in the same algorithm regime.

`THREADS_INCLUDE_CTA=false` remains one environment variable away and takes
every post link-free immediately. It is the switch, available whenever the
answer stops being worth measuring; it just cannot also be the measurement.

## Why the effect might be smaller than the prior suggests

The 30–50% figure everyone quotes comes from Buffer's 18.8M-post analysis of X.
Threads is a different product with a different incentive: Meta has been
explicit that it does not demote outbound links the way X does, and this
account's Threads posts have carried the Substack link the whole time while
averaging reach an order of magnitude above X. `min_effect` is set at 1.3 rather
than 1.5 for that reason — a smaller effect is still worth acting on here,
because Threads volume is large enough that 30% of it is real traffic.

## What closes the card

15 posts per arm, or 2026-11-30, whichever comes first. `scripts/retro_test.py`
reads the arms off the `threads_link_arm` tag; the nightly digest prints the
engagement version with the stale-arm guard, so if one arm stops being assigned
the digest says so instead of reporting the gap.

## Why the status is `open` and not `testing`

`research/experiments.py` allows exactly one card in `testing`, and H-002 holds
that slot. The slot governs *hook* assignment — arms that change what the post
says — and this variable does not touch the hook, so the randomisation runs in
`loops/post_loop.py` from today and the rows accrue either way. The card moves
to `testing` when H-002 closes, which is a bookkeeping change, not the start of
data collection.
