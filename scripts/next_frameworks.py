#!/usr/bin/env python3
"""Rank the framework backlog and write frameworks/next.md.

When the runway alarm fires, "write the next batch" is only useful if choosing
the batch is not itself a fresh decision every time. Left to memory, that
choice is what rotted: the ledger held eight frameworks from one of thirteen
books, so the obvious read of the repo was that the library was nearly spent.

So the choice becomes a regenerated artifact. This ranks every writable
framework on evidence already in the repository and commits the shortlist. At
any moment the repo answers "what is next" without anyone having to remember.

What is mechanical here and what is not:

  Mechanical  which frameworks are even candidates, and their ranking.
  Editorial   the order inside a batch. Each flagship unit closes by teasing
              the next framework, so a batch is a chain, and chains are chosen
              by whoever writes them.

    python scripts/next_frameworks.py           # write frameworks/next.md
    python scripts/next_frameworks.py --check   # fail if the file is stale
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = ROOT / "frameworks" / "index.csv"
OUT = ROOT / "frameworks" / "next.md"

SHORTLIST = 12

# ── scoring ──────────────────────────────────────────────────────────────────
# Every weight below encodes something the series already commits to in
# .claude/skills/x-post/SKILL.md. They are not tuned against measured
# performance, because there is not yet enough of it — see `MIN_PER_CATEGORY`.

# The series is sold as "the tools McKinsey, BCG and Bain actually use", so a
# framework those firms genuinely originated is worth more to it than one where
# the provenance has to be softened to "consultants use this". Naming a firm
# that did not invent the framework is off the table; the skill is explicit
# that the target reader sees through it and it costs more than it buys.
W_FIRM = 3.0
W_AUTHOR = 2.0
W_DATED = 0.5

# How much of the brief is already in investing vocabulary. A framework whose
# source text talks about returns, margins and capital is one where the
# investing lens is a translation; one that never does needs the angle
# invented, which is where thin, generic posts come from.
W_INVESTOR = 0.35
INVESTOR_CAP = 10

# Push against the series becoming one category. Twelve of the first eighteen
# came from three books, and a reader who followed for industry structure has
# no reason to stay for eight straight posts on operating models.
W_CATEGORY_CROWDING = -1.2

MIN_PER_CATEGORY = 5

# Both inputs are read off the ledger, never off frameworks/raw/. The briefs
# are gitignored copyrighted prose, so a ranker that reads them scores every
# framework at zero anywhere but the machine that ran the ingest — and the
# cron then commits that as the shortlist. scripts/build_framework_index.py
# distils the two facts into index.csv on the machine that has the books.
PROVENANCE_WEIGHT = {"firm": W_FIRM, "author": W_AUTHOR, "dated": W_DATED, "none": 0.0}


def score(row: dict, taken_per_category: Counter) -> tuple[float, list[str]]:
    why, total = [], 0.0

    tier = row.get("provenance") or "none"
    total += PROVENANCE_WEIGHT.get(tier, 0.0)
    if tier == "firm":
        why.append("originated by one of the three firms")
    elif tier == "author":
        why.append("named author or institution")
    elif tier == "dated":
        why.append("dated origin only")

    terms = int(row.get("investor_terms") or 0)
    if terms:
        total += W_INVESTOR * min(terms, INVESTOR_CAP)
        why.append(f"{terms} investing term{'s' * (terms != 1)} in source")

    # Counts what is published plus what the greedy pass has already taken, so
    # the wording has to cover both.
    crowding = taken_per_category.get(row["category"], 0)
    if crowding:
        total += W_CATEGORY_CROWDING * crowding
        why.append(f"{crowding} already ahead of it in this category")

    return round(total, 2), why


def build() -> dict:
    rows = list(csv.DictReader(INDEX.open(encoding="utf-8")))
    published = Counter(r["category"] for r in rows if r["status"] == "published")
    candidates = [r for r in rows if r["status"] == "backlog" and r["source"] == "brief"]

    # Greedy, re-scoring after every pick. Scoring the whole backlog once and
    # taking the top twelve looks the same but is not: the crowding penalty
    # then only sees what has already been *published*, so a category with a
    # deep bench sweeps the shortlist and the batch drawn off it is six posts
    # in a row from one book. Charging each pick against its own category as
    # the list is built is what actually spreads it.
    running = Counter(published)
    shortlist, pool = [], list(candidates)
    while pool and len(shortlist) < SHORTLIST:
        scored = [(*score(r, running), r) for r in pool]
        scored.sort(key=lambda x: (-x[0], x[2]["category"], x[2]["slug"]))
        s, why, row = scored[0]
        shortlist.append({**row, "score": s, "why": why})
        running[row["category"]] += 1
        pool.remove(row)

    return {
        "shortlist": shortlist,
        "candidates": candidates,
        "published": published,
        "needs_prose": [r for r in rows if r["status"] == "backlog" and r["source"] != "brief"],
        "total": len(rows),
    }


def render(data: dict) -> str:
    shortlist, published = data["shortlist"], data["published"]
    lines = [
        "# What to write next",
        "",
        "Generated by `scripts/next_frameworks.py` — edit the weights there, not this file.",
        "",
        f"{sum(published.values())} of {data['total']} frameworks published. "
        f"{len(data['candidates'])} more have prose on disk and can be written today; "
        f"{len(data['needs_prose'])} are contents-page entries whose prose still "
        "needs extracting (the Drive reader truncates each PDF around page 80).",
        "",
        "Each framework ships as three files or it ships as nothing: "
        "`units/<slug>.md`, `carousels/<slug>.json`, and ten queries in "
        "`assets/background_queries.json`. `tests/test_framework_parity.py` enforces it.",
        "",
        f"## Shortlist (next {SHORTLIST})",
        "",
        "Picked one at a time on provenance, how much investing vocabulary the "
        "source already carries, and how crowded the category is — each pick "
        "charged against its own category, so the list stays spread. Order "
        "within a batch is an editorial call: each unit closes by teasing the "
        "next one, so a batch is a chain, not a set.",
        "",
        "| # | Framework | Category | Score | Why |",
        "|---|---|---|---|---|",
    ]
    for i, r in enumerate(shortlist, 1):
        lines.append(f"| {i} | {r['name']} | {r['category']} | {r['score']} | "
                     f"{'; '.join(r['why'])} |")

    lines += ["", "## Category balance", "", "| Category | Published | Writable backlog |",
              "|---|---|---|"]
    by_cat = Counter(r["category"] for r in data["candidates"])
    for cat in sorted(set(published) | set(by_cat)):
        lines.append(f"| {cat} | {published.get(cat, 0)} | {by_cat.get(cat, 0)} |")

    lines += [
        "",
        "## Not yet rankable",
        "",
        f"{len(data['needs_prose'])} frameworks appear on a contents page but have "
        "no prose on disk, so they are excluded from the shortlist rather than "
        "ranked at zero. Recovering them means re-reading the PDFs past the "
        "point where the Drive reader truncates, then rerunning "
        "`scripts/ingest_frameworks.py` and `scripts/build_framework_index.py`.",
        "",
        "## When measured performance joins the ranking",
        "",
        f"Category reach stays out of the score until at least {MIN_PER_CATEGORY} "
        "frameworks have shipped in each category being compared. Ranking on two "
        "posts per category would be the same mistake the retro tester refuses to "
        "make, and it would make the ranking look evidence-based while being noise.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="compare against the committed file instead of writing")
    args = ap.parse_args()

    rendered = render(build())
    if args.check:
        committed = OUT.read_text("utf-8") if OUT.exists() else None
        if committed != rendered:
            print("frameworks/next.md is stale — run scripts/next_frameworks.py")
            sys.exit(1)
        print("frameworks/next.md up to date")
        return

    OUT.write_text(rendered, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
