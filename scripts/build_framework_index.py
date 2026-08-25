#!/usr/bin/env python3
"""Rebuild frameworks/index.csv — the ledger of every framework in the series.

Why this exists: the index used to be whatever ingest_frameworks.py happened to
append, which meant it listed 8 frameworks from 1 of the 13 Umbrex books. The
post loop then ran out of drafts and the pipeline looked like it had a content
problem when it only had a bookkeeping one. This script rebuilds the whole
ledger from two sources so that can't drift again:

  1. frameworks/raw/<slug>.md   — briefs split out of a book's prose. The Drive
     reader truncates each PDF around page 80, so a book yields ~8 briefs even
     when its contents page lists more.
  2. BOOK_CONTENTS below        — every name printed in the 13 tables of
     contents, in order. Names past the truncation point have no prose on disk
     yet; they are still real backlog and belong in the ledger.

Published units are matched through UNIT_SLUGS, because a unit filename is a
short handle ("five-forces") while a framework slug is the full book name
("porters-five-forces").

Usage:  python scripts/build_framework_index.py [--check]
        --check exits non-zero instead of writing, for CI.
"""
from __future__ import annotations

import argparse
import csv
import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "frameworks" / "raw"
UNITS_DIR = ROOT / "units"
INDEX = ROOT / "frameworks" / "index.csv"

FIELDS = ["slug", "name", "category", "source", "status", "unit",
          "provenance", "investor_terms"]

# Two facts distilled from each brief so that ranking the backlog never needs
# the brief itself. frameworks/raw/ is gitignored — it is verbatim book prose
# and never gets published — so anything downstream that reads it works only on
# the one machine that ran the ingest. A provenance tier and a term count are
# derived facts about a framework rather than the book's expression, so they
# can live in the committed ledger, and the ranker becomes reproducible in CI.
FIRMS = ("McKinsey", "Boston Consulting Group", "BCG", "Bain")
# Named people and named institutions only. "taught in business schools"
# appears in a fifth of these origins and is a claim about who adopted a
# framework, not who wrote it — the same distinction the x-post skill draws
# before letting a post name anybody.
AUTHORS = (
    "Porter", "Christensen", "Ansoff", "Bowman", "Henderson", "Treacy",
    "Wiersema", "Kim", "Mauborgne", "Grove", "Rogers", "Moore", "Ulwick",
    "Kaplan", "Norton", "Prahalad", "Hamel", "Ghemawat", "Kotter", "Osterwalder",
    "Harvard", "INSEAD", "Stanford", "MIT", "Wharton", "Cranfield",
)
INVESTOR_TERMS = (
    "ROIC", "return on invested capital", "margin", "capital allocation",
    "market share", "valuation", "moat", "profit pool", "cost position",
    "pricing power", "switching cost", "churn", "retention", "cash flow",
    "unit economics", "payback", "shareholder", "EBIT", "capital intensity",
)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")

# Every name on the 13 contents pages, in print order. Transcribed from the
# books; the extractor flattens a contents page into one run-on line, so this
# split is recorded as data rather than re-derived by regex each run.
BOOK_CONTENTS: dict[str, list[str]] = {
    "Industry & Market Structure": [
        "Porter's Five Forces",
        "Extended Five Forces",
        "PEST Analysis",
        "PESTEL / STEEP / STEEPLE Framework",
        "Industry Life Cycle Model",
        "Technology Adoption Life Cycle",
        "S-Curve of Industry / Technology Evolution",
        "Strategic Inflection Point Framework",
        "Market Attractiveness-Competitive Position Matrix",
        "Competitor Response Profile",
        "Market Mapping / Landscape Mapping",
        "Ecosystem Mapping",
    ],
    "Competitive & Business-Level Strategy": [
        "Porter's Generic Strategies",
        "Treacy & Wiersema Value Disciplines",
        "Bowman's Strategy Clock",
        "Porter's Value Chain",
        "Experience Curve",
        "Relative Cost Positioning Framework",
        "Key Success Factors Analysis",
        "Strategic Group Mapping",
        "Game Theory / Co-opetition Framework",
        "Value Net",
        "Delta Model",
        "Resource-Based View",
        "VRIO / VRIN Analysis",
        "Core Competence Framework",
        "PIMS Model",
        "ADL Life Cycle-Competitive Position Matrix",
        "Shell Directional Policy Matrix",
        "BCG Time-based Competition Framework",
        "Profit Pool Mapping",
    ],
    "Corporate & Portfolio Strategy": [
        "BCG Growth-Share Matrix",
        "GE-McKinsey Nine-Box Matrix",
        "BCG Advantage Matrix",
        "Ashridge Portfolio Display",
        "Parenting Advantage Framework",
        "Corporate Scope Matrix",
        "Role of the Center / Corporate Parenting Styles",
        "Make-Buy-Ally / Vertical Integration Framework",
        "Adjacency Expansion Matrix",
        "McKinsey Three Horizons of Growth",
        "Corporate Value Creation Logic",
        "SBU Segmentation Framework",
        "Strategic Control Map",
        "Portfolio Value Gap Analysis",
        "Capital Allocation Framework",
        "Core vs Non-core Portfolio Framework",
        "Restructuring / Portfolio Pruning Framework",
    ],
    "Growth, Innovation & Disruption": [
        "Ansoff Product-Market Growth Matrix",
        "Innovation Ambition Matrix",
        "McKinsey Seven Degrees of Freedom for Growth",
        "Jobs to Be Done Framework",
        "Disruptive Innovation Theory",
        "Blue Ocean Strategy Canvas",
        "Blue Ocean Four Actions Framework",
        "10 Types of Innovation",
        "Stage-Gate Innovation Process",
        "Ambidextrous Organization Framework",
        "Real Options Logic",
        "Platform Launch & Scaling Lifecycle",
        "AARRR Pirate Metrics Funnel",
        "Growth Flywheel Framework",
        "Network Effects Map",
        "MVP Learning Loop",
        "Design Thinking Double Diamond",
    ],
    "Business Model & Value Proposition": [
        "Business Model Canvas",
        "Lean Canvas",
        "Value Proposition Canvas",
        "Operating Model Canvas",
        "Profit Formula Framework",
        "Business Model Patterns Library",
        "Two-sided Platform Business Model",
        "B2B2C Value Chain Mapping",
        "Service-Dominant Logic",
        "Razor-and-Blades Business Model Pattern",
    ],
    "Capabilities, Organization & Operating Model": [
        "McKinsey 7S Framework",
        "Galbraith Star Model",
        "Operating Model 4D",
        "Capability Map",
        "Capability Maturity Model",
        "Span of Control & Layering Analysis",
        "RACI Matrix",
        "Organizational Health Index",
        "Agile Operating Model",
        "Shared Services vs Business Partnering Model",
        "Centers of Excellence Design Framework",
        "Strategic Alignment Model",
    ],
    "Digital, Data, Platforms & Ecosystems": [
        "Digital Maturity Model",
        "Digital Transformation Roadmap",
        "Platform Strategy Framework",
        "Ecosystem Roles Map",
        "API Economy Framework",
        "North Star Metric Framework",
        "Data Monetization Framework",
        "AI Value Creation Framework",
        "Digital Twin Framework",
        "Omnichannel Strategy Framework",
        "Product-Led Growth Framework",
    ],
    "Customer, Marketing & Brand": [
        "STP Framework",
        "4Ps Marketing Mix",
        "7Ps Marketing Mix",
        "Customer Journey Mapping",
        "Customer Lifecycle Framework",
        "Customer Lifetime Value Model",
        "Share of Wallet Framework",
        "Net Promoter System",
        "RFM Segmentation",
        "Kano Model",
        "Moments of Truth Framework",
        "Brand Equity Pyramid",
        "Brand Positioning Map",
        "Brand Archetypes Framework",
    ],
    "Operations, Supply Chain & Efficiency": [
        "Service Blueprinting",
        "Theory of Constraints",
        "Lean Value Stream Mapping",
        "Six Sigma DMAIC",
        "Lean Six Sigma House of Quality",
        "SCOR Model",
        "Capacity Planning Framework",
        "Just-in-Time System",
        "Total Productive Maintenance",
        "Make-Buy Decision Framework",
        "Operations Footprint Optimization",
    ],
    "Risk, Uncertainty & Scenarios": [
        "OODA Loop",
        "War-gaming Framework",
        "Scenario Planning",
        "Risk Heat Map",
        "Risk-Adjusted Return on Capital",
        "Strategic Flexibility Matrix",
        "Real Options Valuation",
        "Decision Tree Analysis",
        "Black Swan / Barbell Strategy",
        "Stress Testing Framework",
    ],
    "International & Global Strategy": [
        "CAGE Distance Framework",
        "AAA Global Strategy Framework",
        "OLI / Eclectic Paradigm",
        "Uppsala Internationalization Model",
        "Market Entry Mode Choice Framework",
        "Global Integration-Local Responsiveness Grid",
        "Global Value Chain Configuration Framework",
    ],
    "Strategy Process, Problem Solving & Decision-Making": [
        "RAPID Decision-rights Framework",
        "Influence Map",
        "Kotter's Eight Steps for Change",
        "Rogers Diffusion of Innovations Curve",
        "Issue Tree",
        "Hypothesis-driven Problem Solving",
        "MECE Principle",
        "Stakeholder Mapping",
        "RASCI Framework",
        "Decision Quality Chain",
        "ADKAR Change Management Model",
        "Strategic Planning Rhythm",
        "Hoshin Kanri",
        "Management Flight Simulators",
        "Lewin's Force Field Analysis",
    ],
    "Social Impact, ESG & Public Value": [
        "Triple Bottom Line",
        "Shared Value Framework",
        "ESG Materiality Matrix",
        "Theory of Change",
        "Logical Framework Approach",
        "Social Return on Investment",
        "Collective Impact Framework",
        "Sustainable Development Goals Mapping",
        "Impact Management Project Dimensions",
        "Stakeholder Capitalism Framework",
    ],
}

# framework slug -> units/<handle>.md, for the ones already published. The unit
# handle is the short public one; the framework slug is the book's full name.
UNIT_SLUGS = {
    # batch 31-34
    "rapid-decision-rights-framework": "rapid-decision-rights",
    "business-model-canvas": "business-model-canvas",
    "organizational-health-index": "organizational-health-index",
    "ecosystem-roles-map": "ecosystem-roles-map",
    # batch 35-38
    "aaa-global-strategy-framework": "aaa-global-strategy",
    "collective-impact-framework": "collective-impact",
    "lean-six-sigma-house-of-quality": "house-of-quality",
    "real-options-valuation": "real-options-valuation",
    "adjacency-expansion-matrix": "adjacency-expansion",
    "customer-lifetime-value-model": "customer-lifetime-value",
    "decision-quality-chain": "decision-quality-chain",
    "mckinsey-seven-degrees-of-freedom-for-growth": "seven-degrees-of-freedom",
    "porters-generic-strategies": "porter",
    "porters-five-forces": "five-forces",
    "bcg-growth-share-matrix": "bcg-matrix",
    "blue-ocean-strategy-canvas": "blue-ocean",
    "disruptive-innovation-theory": "disruptive-innovation",
    "ansoff-product-market-growth-matrix": "ansoff-matrix",
    "porters-value-chain": "value-chain",
    "experience-curve": "experience-curve",
    "strategic-group-mapping": "strategic-group-mapping",
    "bowmans-strategy-clock": "bowmans-strategy-clock",
    "key-success-factors-analysis": "key-success-factors",
    "relative-cost-positioning-framework": "relative-cost-positioning",
    "ge-mckinsey-nine-box-matrix": "ge-mckinsey-matrix",
    "bcg-advantage-matrix": "bcg-advantage-matrix",
    "technology-adoption-life-cycle": "technology-adoption-curve",
    "strategic-inflection-point-framework": "strategic-inflection-point",
    "jobs-to-be-done-framework": "jobs-to-be-done",
    "treacy-wiersema-value-disciplines": "value-disciplines",
    "profit-formula-framework": "profit-formula",
    "net-promoter-system": "net-promoter",
    "kano-model": "kano-model",
    "mece-principle": "mece-principle",
    "mckinsey-7s-framework": "mckinsey-7s",
    "digital-maturity-model": "digital-maturity",
    "lean-canvas": "lean-canvas",
    "make-buy-decision-framework": "make-buy",
    "cage-distance-framework": "cage-distance",
    "shared-value-framework": "shared-value",
    "stress-testing-framework": "stress-testing",
    "core-vs-non-core-portfolio-framework": "core-vs-non-core",
    # The Industry & Market Structure book prints the GE–McKinsey nine-box
    # under its generic name. Same framework, same axes — publishing it twice
    # would be a rehash, so it points at the unit that already shipped.
    "market-attractiveness-competitive-position-matrix": "ge-mckinsey-matrix",
}


def slugify(name: str) -> str:
    s = re.sub(r"[’'\"]", "", name)
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s[:60]


def distil(slug: str) -> tuple[str, int]:
    """(provenance tier, investor-term count) for one brief.

    Tier is `firm` when the origin names one of the three firms the series is
    sold on, `author` when it names a person or institution, `dated` when it
    only carries a year, and `none` otherwise. Naming a firm that did not
    invent a framework is off the table, so the tier is a ceiling on how the
    authority hook can be written, not just a score.
    """
    path = RAW_DIR / f"{slug}.md"
    if not path.exists():
        return "", 0
    text = path.read_text("utf-8")
    m = re.search(r"Origin and Background(.{0,1600})", text, re.S)
    origin = m.group(1) if m else text[:1600]

    if any(f in origin for f in FIRMS):
        tier = "firm"
    elif any(a in origin for a in AUTHORS):
        tier = "author"
    elif _YEAR.search(origin):
        tier = "dated"
    else:
        tier = "none"
    lowered = text.lower()
    return tier, sum(1 for t in INVESTOR_TERMS if t.lower() in lowered)


def build() -> list[dict]:
    briefs = {p.stem for p in RAW_DIR.glob("*.md")} if RAW_DIR.exists() else set()
    if not briefs:
        # Without the briefs every row would be rewritten to source=book-toc
        # and provenance="", which erases the record of what is writable. That
        # is the failure this ledger was built to end, so refuse rather than
        # produce a confident, wrong file.
        raise SystemExit(
            "frameworks/raw/ is empty — run scripts/ingest_frameworks.py on the "
            "source books first. This script rewrites the ledger from the briefs, "
            "so running it without them would erase what is on disk."
        )

    rows, seen = [], set()
    for category, names in BOOK_CONTENTS.items():
        for name in names:
            slug = slugify(name)
            if slug in seen:            # a few names are printed in two books
                continue
            seen.add(slug)
            unit = UNIT_SLUGS.get(slug, "")
            published = bool(unit) and (UNITS_DIR / f"{unit}.md").exists()
            tier, terms = distil(slug)
            rows.append({
                "slug": slug,
                "name": name,
                "category": category,
                "source": "brief" if slug in briefs else "book-toc",
                "status": "published" if published else "backlog",
                "unit": unit if published else "",
                "provenance": tier,
                "investor_terms": terms,
            })
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="compare against the committed index instead of writing")
    args = ap.parse_args()

    rows = build()

    sio = io.StringIO()
    w = csv.DictWriter(sio, fieldnames=FIELDS, lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    rendered = sio.getvalue()

    if args.check:
        committed = INDEX.read_text(encoding="utf-8") if INDEX.exists() else None
        if committed != rendered:
            print("frameworks/index.csv is stale — run scripts/build_framework_index.py")
            sys.exit(1)
        print(f"index.csv up to date ({len(rows)} frameworks)")
        return

    INDEX.write_text(rendered, encoding="utf-8")
    published = sum(r["status"] == "published" for r in rows)
    with_prose = sum(r["source"] == "brief" for r in rows)
    print(f"{len(rows)} frameworks -> {INDEX.relative_to(ROOT)}")
    print(f"  published: {published}")
    print(f"  brief on disk, unwritten: {with_prose - published}")
    print(f"  contents page only: {len(rows) - with_prose}")


if __name__ == "__main__":
    main()
