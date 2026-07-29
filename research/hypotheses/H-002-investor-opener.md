---
id: H-002
status: open
source: own-metrics
created: 2026-07-29
claim: >
  On Threads, an opening line about the reader's own position — a holding, its
  margin, its valuation — reaches more people than one that opens on a scene or
  a case study.
variable:
  key: investor_opener
  scorer: investor_opener
  arms: [yes, no]
prediction:
  metric: impressions
  platform: Threads
  direction: yes > no
  min_effect: 1.5
  n_per_arm: 12
  block_by: framework
  stop_by: 2026-10-15
confounds:
  - >
    Aligned with H-001 in the current corpus: the same Blue Ocean post is both
    the scene-opener and the one without early provenance. Until one of the two
    is varied on its own, a result for either is a result for both.
---

# H-002 — whose situation the first line is about

Blue Ocean opened on a circus with no animals. In an investing feed a reader
scrolling past sees a sentence that appears to be about someone else's business,
and keeps scrolling. Every other framework post opened on something the reader
might own.

This is the sibling of H-001 and the two cannot be separated by looking at
history, because in the corpus they take the same value on the same posts. One
of them has to be varied alone.

Running order matters: H-001 first, because provenance is cheap to move (the
same sentence, one paragraph later) while rewriting an opening from scene to
holding changes the post itself and drags other variables with it.

## Retro result — 2026-07-29 — still-thin, best candidate so far

`yes` n=5 (mean 7,290), `no` n=2 (mean 2,561), ratio 2.85x, 90% CI [0.99, 9.98].

The `no` arm is Blue Ocean (985, opens on a circus) and Disruptive Innovation
(4,137, opens on Netflix posting DVDs in red envelopes). Both open on somebody
else's business. The five `yes` posts open on the reader's.

Two observations per arm, a CI that touches 1.0, and arms that barely overlap in
time. This is a direction to test, not a result. But it survived the pass that
killed H-001's premise, which promotes it to first in the queue.
