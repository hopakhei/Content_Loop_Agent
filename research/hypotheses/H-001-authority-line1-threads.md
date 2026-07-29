---
id: H-001
status: open
source: own-metrics
created: 2026-07-29
claim: >
  On Threads, a root post whose first line names a recognisable firm, author or
  institution reaches more people than one whose opening line carries no
  provenance.
variable:
  key: authority_line1
  scorer: authority_line1
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
    The observation that started this compared BCG matrix, Bowman and Blue Ocean
    — three different frameworks. Framework identity is by far the largest
    source of variance on this account and it is perfectly aligned with the
    variable in that comparison.
  - >
    Blue Ocean opened on a circus rather than on the reader's own holding, so
    its low reach has a second explanation (see H-002).
---

# H-001 — provenance in the first line (Threads)

## Where this came from

Threads truncates the feed preview after two or three lines, so the opening line
is the only text most readers ever see. Three framework posts in the same week
came out very far apart, and the ordering matched how early the provenance
appeared.

## Why it cannot be settled by looking harder at what we have

Every unit in `units/` now opens with provenance, because
`tests/test_framework_parity.py::test_every_framework_hook_carries_an_authority_signal`
requires it. That test was added before this hypothesis was written down, which
means the corpus has no negative arm left: enforcing the rule removed the
variation needed to check it.

This is the part worth remembering. A rule adopted from an unmeasured hunch and
then enforced in CI stops looking like a hunch — it becomes invisible, because
no counter-example can ever be produced again.

## What a real test looks like

Randomise the opening line of the flagship Thread between a provenance-carrying
version and one that states the same investor problem with the attribution moved
to the second paragraph. Both versions are true; only the position changes. Block
by framework so the same framework contributes to both arms across its Threads
and X postings.

Requires relaxing the parity test to accept a documented experimental arm.

## Cost

At one post a day, 12 per arm is roughly six weeks. That is the real price of
having enforced the rule first.

## Retro result — 2026-07-29 — still-thin, and the premise did not survive

`yes` n=1 (mean 7,658), `no` n=6 (mean 5,653), ratio 1.35x, 90% CI [0.72, 3.60].

The number is not the finding. The finding is what showed up while getting it.

Scored against the units as they actually shipped (git history, not the working
tree), **BCG matrix and Bowman fall in the same arm.** Both carry their
provenance in the second paragraph and neither names anyone in line 1:

    bcg-matrix   一間正在賺錢的公司，可能已經在死。          19,115
    bowmans      高毛利有兩種，一種守得住，一種在倒數。        1,540

Those two posts are the comparison the rule in `.claude/skills/x-post/SKILL.md`
(鐵律零點五) was built on. They are identical on the variable the rule is about,
and 12x apart. Whatever separates them, it is not where the provenance sits.

The 914 / 314 / 118 figures in that skill are still real measurements. The causal
reading attached to them is not supported.

Next: H-002 is the surviving candidate on this data. Do not restate the
provenance rule as settled in the meantime — leave it in the skill as the current
default, flagged as untested.
