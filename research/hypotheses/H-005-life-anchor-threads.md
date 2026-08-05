---
id: H-005
status: abandoned
created_closed: 2026-08-05
source: intuition
created: 2026-08-01
claim: >
  On Threads, a post whose argument travels through an everyday scene — a
  milkshake on a commute, the queue at a restaurant — earns more engagement
  per view than one that stays inside boardrooms and balance sheets. The
  Threads audience skews casual; a reader who would never open an annual
  report will still argue about why the queue outside one bakery never
  shortens.
variable:
  key: life_anchor
  scorer: life_anchor
  arms: ["yes", "no"]
prediction:
  metric: engagement_rate
  platform: Threads
  direction: yes > no
  min_effect: 1.3
  n_per_arm: 12
  block_by: framework
  stop_by: 2026-11-30
confounds:
  - >
    Framework choice. A life-anchored treatment is easier to write for JTBD or
    Net Promoter than for the GE-McKinsey capital-allocation grid, so arm
    membership will correlate with topic. block_by framework limits this but
    cannot remove it; the honest comparison is within frameworks that could
    have been written either way.
  - >
    H-002 overlap. The scene-opener arm of H-002 will often also be
    life-anchored. The variables are defined to be independent (H-002 reads
    line 1, this reads the whole body), but while both move at once a result
    for either is partly a result for both. This card therefore stays `open`
    until H-002 reaches a verdict — one live experiment at a time.
  - >
    The body is shared across X and Threads, so the treatment cannot be
    randomised per platform per day. The design is a corpus comparison, not a
    coin flip: some upcoming units are written life-anchored, some are not,
    and the retro pass scores them after four weeks of exposure.
---

# H-005 — arguments that travel through ordinary life

The owner's observation, 2026-08-01, verbatim intent: Threads readers are
there to be entertained, not briefed. The instinct arrived independently but
matches the one live experiment: H-002's scene arm is the opening-line version
of exactly this claim, with one tagged data point so far.

This card pre-registers the broader, body-level version so that whichever way
the upcoming batch is written, the question stays a measurement rather than a
vibe. The JTBD unit (milkshake, bananas, commutes) is the strongest existing
life-anchored treatment and posts in the coming week; the GE-McKinsey unit
(annual reports, capital allocation) is its natural opposite and posted today.
Those two are the pilot pair.

## Design notes

Written life-first does not mean written softer. The rule from H-002 carries
over: both treatments must be equally well made, because a deliberately weak
control measures writing effort, not framing. A unit whose framework has no
honest everyday angle is written straight and lands in the `no` arm — forcing
a milkshake into the capital-allocation grid would be the same sin as writing
the control badly.

Engagement per view, not reach, is the metric: the claim is that casual
readers interact more when the argument lives where they live, and rate is
the version of that claim least confounded by follower growth and the
framework-era reach shift (H-004).

Promotion path: when H-002 closes, this card inherits the live slot if its
retro pass by then still shows a direction worth the posting slots.

## Trial corpus — batch 19–30, written 2026-08-01

The batch the owner asked to "try a few posts" with. Four units are written
life-anchored and lead the chain (profit-formula 早餐店, net-promoter 餐廳,
kano-model 手機, mece-principle 行李); the other eight are written straight
and verified free of every LIFE_NOUN, so the `no` arm is clean rather than
accidental. Scorer-checked before commit: all twelve land in their intended
arm under either H-002 hook, so the two experiments stay independent in this
corpus. Both treatments follow the H-002 rule — equally well made.

## Closed — 2026-08-05 — abandoned, decided editorially before it was measured

The owner watched the milkshake post (`jobs-to-be-done`) land and made life
anchoring a standing rule for every post on every platform. That settles the
question as a product decision, and it ends this card, because the `no` arm is
now something the style rule forbids anybody to write. An experiment whose
control is banned is not an experiment.

Abandoned, not supported. Nothing here was measured:

- The milkshake post went out 2026-08-04 05:30 UTC. Its impressions were still
  blank in Post Performance when this card was closed — metrics need 24h plus
  the next nightly LEARN. The decision rests on what the owner saw in the app,
  which is real evidence and is not evidence this repo holds.
- The retro corpus never had enough to say anything: at close, six of thirty
  frameworks carried any life scene at all, and only one of those had a
  measured Threads row.

What the rule replaced the experiment with is `scripts/audit_grounding.py`,
which grades every unit, carousel and caption on all three channels and fails
the build on anything unpublished that opens away from the reader. A style rule
nobody checks is a style rule that decays; that script is the part of this card
that survives.

**If the direction is ever worth measuring again**, it cannot be done by writing
some posts flat — the rule forbids it. It would have to be a comparison of
*where* the scene sits (opening vs middle), which is a different card.
