#!/usr/bin/env python3
"""Ingest an Umbrex "Strategy Frameworks" PDF (already extracted to text) into
one structured brief per framework.

The editorial step (brief -> investing-lens carousel + units) stays human — this
script only does the deterministic part: split a book into per-framework briefs
so the backlog is ready. Every framework in these books follows the same 9-part
anatomy, so the split is a clean regex on the "1. What Is X?" anchors.

Usage:
    python scripts/ingest_frameworks.py <raw_text_file> --category "Competitive"

<raw_text_file> is the plain text of one PDF (the fileContent from the Drive
reader). Writes frameworks/raw/<slug>.md, which is gitignored: it is verbatim
book prose and never gets published.

This writes briefs only. frameworks/index.csv has one writer,
scripts/build_framework_index.py — run it afterwards to refresh the ledger.
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "frameworks" / "raw"

# Each framework body opens with its name on a line, then "1. What Is <name>?".
# A leading digit is allowed because some names start with one ("4Ps Marketing
# Mix", "10 Types of Innovation") — anchoring on [A-Z] alone silently drops them.
# The running-head line only marks where a section starts; the name comes from
# the "What Is" sentence, which is the one the books get right. Two books
# disagree with their own running heads (the Operations book heads the
# omnichannel section "Theory of Constraints"; the ESG book appends "Explained"
# to every head), and taking the head at face value mislabels those briefs.
ANCHOR = re.compile(r"\n([A-Z0-9][^\n]{2,70}?)\n+\d\\?\.\s+What Is\s+(.+?)\?", re.M)
FOOTER = re.compile(r"Find an independent consultant.*?Strategy Frameworks", re.S)


def slugify(name: str) -> str:
    s = re.sub(r"[’'\"]", "", name)
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s[:60]


def clean_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    return re.sub(r"^(?:the|The)\s+", "", name)


def split_frameworks(text: str) -> list[tuple[str, str]]:
    """Return [(name, body)] — body runs from one anchor to the next."""
    marks = [(m.start(), clean_name(m.group(2))) for m in ANCHOR.finditer(text)]
    out = []
    for i, (pos, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        body = FOOTER.sub("", text[pos:end]).strip()
        # Drop obvious non-frameworks (TOC echoes are shorter than a real body).
        if len(body) > 800:
            out.append((name, body))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("raw_text_file")
    ap.add_argument("--category", required=True)
    args = ap.parse_args()

    text = Path(args.raw_text_file).read_text(encoding="utf-8")
    # If handed the Drive JSON wrapper, unwrap it.
    if text.lstrip().startswith("{"):
        import json
        text = json.loads(text).get("fileContent", text)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    frameworks = split_frameworks(text)

    for name, body in frameworks:
        path = RAW_DIR / f"{slugify(name)}.md"
        path.write_text(f"# {name}\n\n- category: {args.category}\n\n{body}\n",
                        encoding="utf-8")

    print(f"{len(frameworks)} frameworks -> {RAW_DIR} (category={args.category})")
    for name, _ in frameworks:
        print("  -", name)
    print("now run: python scripts/build_framework_index.py")


if __name__ == "__main__":
    main()
