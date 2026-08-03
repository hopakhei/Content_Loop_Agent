# The auto-producer's standing orders

This file is the whole job. The Routine's prompt should say little more than
"read frameworks/AUTOPRODUCER.md and do what it says", because every time the
rules lived in the prompt instead of here, the prompt drifted out of date and
the run produced something the pipeline rejected — or, more often, nothing.

## Why the first four runs produced nothing

The Routine fired four times between 2026-07-23 and 2026-08-01 and committed
zero units. The prompt told it to write frameworks from `frameworks/raw/`.
That directory is gitignored — it is verbatim book prose, and it only exists
on a machine that has processed the source PDFs. A session cloned fresh from
git sees an empty repo where its source material should be.

So the job was impossible, and it failed the way everything else in this
pipeline fails: quietly, with a green tick.

`frameworks/factsheets/` is the fix. Those are own-words Chinese distillations,
safe to commit, written by a session that *does* have the briefs. They are what
you write from. Never look for `frameworks/raw/` — on your machine it is not
there, and its absence is not an error to report.

## What to write

`frameworks/next.md` ranks the backlog. Take the top entries **that have a fact
sheet in `frameworks/factsheets/<slug>.md`** — that file is the whole of your
source material, and a shortlist entry without one is not writable by you.

If no shortlist entry has a fact sheet, stop and say so plainly in the run
output. Do not invent the framework's history from memory: this series is sold
on its provenance, and a wrong attribution costs more than a missed day.

## What a framework ships as

Four things, or it ships as nothing. There is no code path linking them, so
omitting one is silent — it just makes a channel go quiet later.

| File | Feeds |
|---|---|
| `units/<slug>.md` | X + Threads |
| `carousels/<slug>.json` | Instagram |
| ten queries in `assets/background_queries.json` | the slide photos |
| a line appended to `queue/carousel_queue.txt` | the drip order |

Do **not** touch `frameworks/index.csv`. It is rebuilt by
`scripts/build_framework_index.py` on a machine with the briefs; hand-editing it
puts the ledger and the library out of sync, which is the bookkeeping failure
that started all of this.

## The unit file

Read two shipped units first — `units/value-disciplines.md` and
`units/profit-formula.md` — and match them. The shape that matters:

- A comment header (the parser ignores everything above the first `---`).
- `【N】【Thread】【X + Threads】` where **N is the framework's position in the
  series**. Count the non-numeric files in `units/` and continue from there.
  N becomes `Argument #` in Notion, which is what orders the posts. Getting it
  wrong is how #14 once posted before #13.
- `Hook A（反共識）`, `Hook B（場景開場・H-002 實驗臂）`, `Hook C（懸念缺口）`.
- `Post Body：` then the body, segments separated by `---`, ending `{CTA_URL}`.

One framework is **one flagship thread**. Do not cut it into several rehash
units — that rule changed after the early batches and old prompts still carry
the old number.

## The two live experiments

Both are pre-registered in `research/hypotheses/`. A unit that breaks them is
worse than a unit that never shipped, because it contaminates a comparison that
takes months to collect.

**H-002 — hook arms.** Hook A must score `investor_opener = yes` (it names the
reader's own position: 公司, 股, 毛利, 估值, 財報, 護城河…). Hook B must score
`no` (it opens on a scene, a year, someone else's business). A unit that cannot
produce both arms sits the experiment out — it does not get a half-hearted arm.

**H-005 — life anchoring.** The fact sheet names a suggested arm. `yes` means
the body should travel through an everyday scene; `no` means it is written
straight and must contain **none** of `research/scorers.py: LIFE_NOUNS`.
Both arms must be equally well written — a deliberately weak control measures
writing effort, not framing.

Check both before committing:

```
python - <<'EOF'
import re, pathlib
from research.scorers import investor_opener, life_anchor
t = pathlib.Path("units/<slug>.md").read_text("utf-8")
A = re.search(r"Hook A（[^）]*）：(.+)", t).group(1)
B = re.search(r"Hook B（[^）]*）：(.+)", t).group(1)
body = t[t.index("Post Body：")+10:].replace("{CTA_URL}","")
for h, want in ((A,"yes"), (B,"no")):
    row = {"text": h + "\n\n" + body}
    print(investor_opener(row), want, "| life:", life_anchor(row))
EOF
```

## The entry point: start from the reader, not from the framework

This is the rule most likely to be broken, and it outranks anything else about
style. The full version is 鐵律零點六 in `.claude/skills/x-post/SKILL.md`,
including a rack of beginner myths to open on. The short version:

**The reader is a beginner who wants to invest and knows almost nothing.** Not
a fund manager. They cannot read a balance sheet yet, but they have money they
want to put somewhere, a stock they are eyeing, and a pile of plausible-sounding
beliefs they cannot justify.

Every opening must be one of three things: something in the reader's own life,
a beginner's confusion or myth, or the position they already hold. A framework's
history, a boardroom, or a year is **not** an entry point — those belong in the
second or third segment. Provenance still comes early, but in the back half of
the first sentence or in the second: hook the reader first, then borrow the name.

And every unit needs at least one sentence, with the reader as the subject,
saying what they can actually do next — which stock, which page, which question.
"投資者可以用它來分析公司" is not that sentence.

This applies to **both** H-002 arms. Arm A opens on the reader's own holding;
arm B opens on a scene the reader lives in — not on a scene from 1937.

## Voice and accuracy

The skills in `.claude/skills/` are the voice: `x-post` for the thread,
`ig-carousel` for the deck, `ig-caption` for the caption, `content-anti-ai`
and `renhua` for the de-AI pass. Run the de-AI pass — nobody reviews this
before it publishes.

Two rules that override anything a prompt might say:

- **Traditional Chinese, readable in Taiwan. No Cantonese or HK-specific
  vocabulary in published text.** The comment header above the first `---` is
  working notes and may be Cantonese; everything the parser reads is not.
- **Never attribute a framework to McKinsey, BCG or Bain unless they built it.**
  The fact sheet's `provenance` line is a ceiling, not a suggestion. `firm`
  means you may name the firm; `author` means name the author instead; `dated`
  and `none` mean lean on the era or on "顧問業通用", and name nobody.

Hook A must carry a real authority signal — the firm, the author, or the
institution. `tests/test_framework_parity.py` fails the build if it does not.

## The comment CTA

The carousel CTA and caption ask for the keyword **「案例」**, not 「全文」.
The DM loop watches 全文/框架/案例; 案例 is the one this series uses.

## Before committing

```
python scripts/next_frameworks.py
python -m pytest -q
python -c "
from services.imagecard import load_carousel_spec, render_carousel
render_carousel(load_carousel_spec('carousels/<slug>.json'), '/tmp/preview-<slug>')"
```

The render is not optional: it is the only check that the slide text actually
fits. Then commit and push to `claude/loop-product-spec-y45pgi`.

`generate-pending.yml` turns the units into Notion drafts twice a day and
`fetch-backgrounds.yml` collects the photos nightly, so a pushed batch needs no
further help from you.

## If you cannot finish

Commit what is complete — a framework with all four files is shippable on its
own. Never commit a partial framework (a unit with no carousel, or a queue line
with no spec): `tests/test_runway.py` fails on it, and worse, it makes the
runway meter read deeper than it is.

Say in the run output what you wrote and what you skipped. A run that reports
"wrote 3 of 12, stopped because the fact sheets ran out" is a good run. A run
that reports success and produced nothing is the failure this whole file exists
to end.
