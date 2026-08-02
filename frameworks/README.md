# The framework pipeline

The strategy-framework series is the only thing X, Threads and Instagram
publish. It has run dry twice. This file is the standing procedure that exists
so it does not run dry a third time.

## What went wrong, both times

The pipeline has one characteristic failure and it is not a crash.

- **2026-07-24.** Ten carousels shipped while `units/` still held two
  frameworks. Instagram kept dripping; X and Threads had nothing to post. The
  post loop ran on schedule, found no eligible draft, logged a notice, exited
  zero. No error, for a day.
- **2026-08-01.** All 32 framework drafts were Posted and the carousel queue
  was empty. Same silent exit, three seconds, green tick.

Underneath the second one was a bookkeeping failure. `frameworks/index.csv`
held eight frameworks from one of thirteen source books, so the honest read of
the repository was that the library was nearly spent. It was not: 165
frameworks exist, 84 of them with prose already on disk. The backlog was never
the constraint; the record of the backlog was.

Both failures share a shape: **a scheduled job produced nothing and reported
success.** Everything below is built against that shape.

## The four files a framework needs

A framework ships as all of these or it ships as nothing. There is no code path
linking them, so omitting one is silent — it just makes a channel go quiet.

| File | Feeds |
|---|---|
| `units/<slug>.md` | X + Threads, via generate-pending → post loop |
| `carousels/<slug>.json` | Instagram, via carousel-drip |
| ten queries in `assets/background_queries.json` | the slide photos |
| a line in `queue/carousel_queue.txt` | puts the carousel in the drip order |

`tests/test_framework_parity.py` fails the build when the first three are out
of step. `tests/test_runway.py` fails it when the queue names a carousel that
does not exist, and when a written unit is missing from the ledger.

## The loop that keeps it fed

**1. The gauge.** `scripts/runway.py` counts what is actually queued and
divides by one a day. It appears at the bottom of `state/performance_digest.md`
every night, so the number is visible before it is a problem.

**2. The alarm.** `runway.yml` runs at 02:00 UTC, before the 04:30 publishing
slot, and **fails the job** when either channel drops under
`runway.WARN_DAYS` (5). A failing Actions job emails; a quiet channel does not.
It keeps failing daily until somebody writes the next batch, which is the
intended amount of nagging.

`WARN_DAYS` and `BATCH_DAYS` are a matched pair. A batch has to clear the floor
with room to spare, or the alarm fires the day after every batch and gets
muted — and a muted alarm is worse than none, because it still looks like
coverage. A test pins the relationship.

**3. The answer.** `scripts/next_frameworks.py` ranks every framework that has
prose on disk and writes `frameworks/next.md`. The same cron regenerates and
commits it, so when the alarm fires the question "write what?" is already
answered in the repository. Ranking is on provenance (does the source name the
firm or the author the series is sold on), on how much investing vocabulary the
source text already carries, and on category crowding — each pick charged
against its own category so a batch does not come out as six posts from one
book.

Both scoring inputs are columns in `index.csv`, distilled from the briefs by
`build_framework_index.py` on a machine that has them. The ranker never opens
`frameworks/raw/`, and a test enforces that: the briefs are gitignored, so a
ranker that read them would score every framework at zero everywhere else — and
the cron would commit that as the shortlist. It did exactly that once.

For the same reason `build_framework_index.py` refuses to run when
`frameworks/raw/` is empty. Rewriting the ledger without the briefs would mark
all 102 writable frameworks as contents-page-only and blank every provenance
tier, erasing the record the ledger exists to keep.

What the ranker deliberately does not do: order the batch. Each flagship unit
closes by teasing the next framework, so a batch is a chain, and choosing the
chain is editorial.

What it also does not do yet: rank on measured performance. That waits until at
least `MIN_PER_CATEGORY` frameworks have shipped per category being compared.
Ranking categories on two posts each would make the shortlist look
evidence-based while being noise — the same error `scripts/retro_test.py`
refuses to make.

## Writing a batch

1. `python scripts/runway.py` — see where you are.
2. Read `frameworks/next.md`, take the top ~12, and put them in an order where
   each one hands off to the next.
3. For each: read `frameworks/raw/<slug>.md` (gitignored — it is verbatim book
   prose and never gets published), then write the four files. The voice rules
   are in `.claude/skills/x-post/SKILL.md` and `.claude/skills/ig-carousel/SKILL.md`;
   run the de-AI pass in `.claude/skills/content-anti-ai/SKILL.md` before shipping.
4. `python scripts/build_framework_index.py` — add each new unit to `UNIT_SLUGS`
   first, or the ledger will keep counting it as unwritten.
5. `python scripts/next_frameworks.py && python -m pytest -q`, then run the
   suite once more with `frameworks/raw/` moved aside. CI never has that
   directory, so a test that touches it passes locally and fails there — which
   has now happened twice, both times on this system's own checks.
6. Commit, push. `generate-pending.yml` turns the units into Notion drafts twice
   a day; `fetch-backgrounds.yml` collects the photos nightly.

## Feeding the hands-off path

Everything above assumes whoever writes the batch can read
`frameworks/raw/`. The auto-producer Routine cannot: those briefs are
gitignored, so a session cloned fresh from git sees an empty shelf where its
source material should be. That is why the Routine fired four times and
committed nothing — the job it was given was impossible, and it failed the way
everything else here fails, silently and green.

`frameworks/factsheets/<slug>.md` closes that gap. Each is an own-words Chinese
distillation — origin and provenance tier, mechanism, investor angle, pitfalls,
and the suggested H-005 arm — safe to commit because none of it is book prose.
It carries everything needed to write the four files, and nothing that cannot
be published.

Only a session that has the briefs can write one, so they are a consumable
inventory like the drafts, and `runway.py` meters them separately against
`FACTSHEET_FLOOR`. When the alarm names the fact sheets, the fix is not to
write another batch — it is to top up the shelf so the Routine can.

`frameworks/AUTOPRODUCER.md` is what the Routine reads. Keep the rules there
rather than in its prompt: every time they lived in the prompt they drifted,
and a drifted prompt produces work the pipeline rejects.

## Getting more source material

Thirteen Umbrex books sit in a Google Drive folder. 102 frameworks have prose
extracted into `frameworks/raw/`; the other 63 are contents-page entries only,
because the Drive reader truncates each PDF around page 80 (~146k characters).
Recovering them means reading the PDFs by another route, then rerunning
`scripts/ingest_frameworks.py` per book and `scripts/build_framework_index.py`.

At one post a day, the 84 already-extracted frameworks are about three months
of content. That is the reason the truncation is not urgent — and the reason to
fix it before it is. `runway.py` carries a second floor for exactly this: when
the writable pile drops below `RESERVE_FLOOR` (two batches) the check starts
failing on the reserve, months before the shortlist would come back empty.
