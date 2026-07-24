#!/usr/bin/env python3
"""Ingest an Umbrex "Strategy Frameworks" PDF (already extracted to text) into
one structured brief per framework, plus a master index/queue.

The editorial step (brief -> investing-lens carousel + units) stays human — this
script only does the deterministic part: split a book into per-framework briefs
so the backlog is ready. Every framework in these books follows the same 9-part
anatomy, so the split is a clean regex on the "1. What Is X?" anchors.

Usage:
    python scripts/ingest_frameworks.py <raw_text_file> --category "Competitive"

<raw_text_file> is the plain text of one PDF (the fileContent from the Drive
reader). Writes frameworks/raw/<slug>.md and appends frameworks/index.csv.
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "frameworks" / "raw"
INDEX = ROOT / "frameworks" / "index.csv"

# Each framework body opens with its name on a line, then "1. What Is <name>?".
# The name capture is greedy-safe: stop at the question mark.
ANCHOR = re.compile(r"\n([A-Z][^\n]{2,70}?)\n+\d\\?\.\s+What Is\b", re.M)
FOOTER = re.compile(r"Find an independent consultant.*?Strategy Frameworks", re.S)


def slugify(name: str) -> str:
    s = re.sub(r"[’'\"]", "", name)
    s = re.sub(r"[^A-Za-z0-9]+", "-", s).strip("-").lower()
    return s[:60]


def split_frameworks(text: str) -> list[tuple[str, str]]:
    """Return [(name, body)] — body runs from one anchor to the next."""
    marks = [(m.start(), m.group(1).strip()) for m in ANCHOR.finditer(text)]
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
    ap.add_argument("--priority", default="", help="optional launch-priority tag")
    args = ap.parse_args()

    text = Path(args.raw_text_file).read_text(encoding="utf-8")
    # If handed the Drive JSON wrapper, unwrap it.
    if text.lstrip().startswith("{"):
        import json
        text = json.loads(text).get("fileContent", text)

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    frameworks = split_frameworks(text)

    new_index = INDEX.exists()
    with INDEX.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if not new_index:
            w.writerow(["slug", "name", "category", "status", "priority"])
        for name, body in frameworks:
            slug = slugify(name)
            path = RAW_DIR / f"{slug}.md"
            path.write_text(f"# {name}\n\n- category: {args.category}\n\n{body}\n",
                            encoding="utf-8")
            w.writerow([slug, name, args.category, "raw", args.priority])

    print(f"{len(frameworks)} frameworks -> {RAW_DIR} (category={args.category})")
    for name, _ in frameworks:
        print("  -", name)


if __name__ == "__main__":
    main()
