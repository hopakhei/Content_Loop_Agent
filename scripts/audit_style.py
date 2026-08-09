#!/usr/bin/env python3
"""Two things a reader feels immediately and no test was watching.

**Shape.** A framework unit is one story, not an inventory of everything known
about the framework. The batch drifted to nine segments — origin, mechanism,
mechanism, scene, error, approach, investor angle, caveat, close — nine
subjects with no spine, which reads as a list even when every line is true.

**The de-AI list.** `.claude/skills/renhua/SKILL.md` bans a specific set of
phrases. The de-AI pass has been catching the loud half (真正, 其實, 先別) and
missing the common half: at the time this was written the corpus held 33 uses
of 東西 and 19 of 這件事, the two vague-referent bans, against a single 其實.
A rule enforced by whoever remembers it is enforced on the memorable clauses.

    python scripts/audit_style.py            # full table
    python scripts/audit_style.py --check    # exit 1 on any unit

Unlike the grounding audit, this one has no grandfather clause: a unit file is
always editable, and it doubles as the specification the auto-producer copies
when AUTOPRODUCER.md tells it to read two shipped units and match them.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.parsing import parse_units          # noqa: E402

UNITS = ROOT / "units"
POSTED = ROOT / "state" / "posted_units.txt"

# One story, five beats: the reader's situation, the framework, the turn, what
# to do with it, the judgement. More than this and the piece stops having a
# spine — every extra segment is another subject competing for the same reader.
MAX_SEGMENTS = 5

# A segment short enough to be a bullet is a bullet. The floor is what stops
# somebody satisfying MAX_SEGMENTS by merging nine stubs into five.
MIN_SEGMENT_CHARS = 110
# Threads breaks at 500. Past roughly this, a segment is two segments.
MAX_SEGMENT_CHARS = 260

# The renhua ban list, in the Traditional forms this channel publishes in.
# Each entry is (label, pattern). Kept as data so the report can name the rule
# that fired rather than printing a regex at whoever has to fix it.
BANS: list[tuple[str, re.Pattern]] = [
    ("二元對比殼「不是…而是」", re.compile(r"不是[^。！？\n]{0,18}而是")),
    ("二元對比殼「並非…而是」", re.compile(r"並非[^。！？\n]{0,18}而是")),
    ("二元對比殼「不在於…在於」", re.compile(r"不在於[^。！？\n]{0,18}在於")),
    ("二元對比殼「不只是/不僅…更」", re.compile(r"(不只是|不僅)[^。！？\n]{0,18}(更|還)")),
    ("二元對比殼「與其…不如」", re.compile(r"與其[^。！？\n]{0,18}不如")),
    ("命令式開場", re.compile(r"(先別|別急著|順序別反了|別搞反了|記住這句話)")),
    ("偽洞察標記", re.compile(r"(真正|其實|本質上|核心在於|關鍵在於|說白了|歸根結底|更重要的是|這說明|這背後)")),
    ("空泛比較", re.compile(r"(更適合|更自然|更高級)")),
    ("含糊指代「東西」", re.compile(r"東西")),
    ("含糊指代「這件事」", re.compile(r"這件事")),
]


def framework_slugs() -> list[str]:
    return sorted(p.stem for p in UNITS.glob("*.md") if not p.stem.isdigit())


def posted_slugs() -> set[str]:
    if not POSTED.exists():
        return set()
    return {ln.strip() for ln in POSTED.read_text("utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")}


def segments(body: str) -> list[str]:
    return [s.strip() for s in body.split("\n---\n") if s.strip()]


def audit(slug: str) -> dict:
    unit = parse_units((UNITS / f"{slug}.md").read_text("utf-8"))[0]
    body = unit.post_body.replace("{CTA_URL}", "").strip()
    segs = segments(body)
    text = " ".join(list(unit.hooks.values()) + [body])

    bans = []
    for label, rx in BANS:
        found = rx.findall(text)
        if found:
            bans.append((label, len(found)))

    lens = [len(s) for s in segs]
    return {
        "slug": slug,
        "segments": len(segs),
        "too_long": [i + 1 for i, n in enumerate(lens) if n > MAX_SEGMENT_CHARS],
        "too_short": [i + 1 for i, n in enumerate(lens) if n < MIN_SEGMENT_CHARS],
        "bans": bans,
        "ok": (len(segs) <= MAX_SEGMENTS and not bans
               and all(MIN_SEGMENT_CHARS <= n <= MAX_SEGMENT_CHARS for n in lens)),
    }


def problems(row: dict) -> list[str]:
    out = []
    if row["segments"] > MAX_SEGMENTS:
        out.append(f"{row['segments']} segments (max {MAX_SEGMENTS}) — "
                   "one story, not a list of everything known")
    if row["too_long"]:
        out.append(f"segment(s) {row['too_long']} over {MAX_SEGMENT_CHARS} chars")
    if row["too_short"]:
        out.append(f"segment(s) {row['too_short']} under {MIN_SEGMENT_CHARS} chars "
                   "— a segment that short is a bullet")
    for label, n in row["bans"]:
        out.append(f"{label} ×{n}")
    return out


def render(rows: list[dict], posted: set[str]) -> str:
    out = ["Style audit — story shape and the de-AI list", "",
           f"{'framework':30}{'segs':>5}{'bans':>6}  state"]
    out.append("-" * 60)
    for r in rows:
        state = "published" if r["slug"] in posted else "still fixable"
        n_bans = sum(n for _, n in r["bans"])
        flag = "" if r["ok"] else "  <-"
        out.append(f"{r['slug']:30}{r['segments']:>5}{n_bans:>6}  {state}{flag}")
    out += ["",
            f"{sum(1 for r in rows if r['ok'])}/{len(rows)} clean. "
            "The state column is context, not an exemption — every unit is graded."]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 when any unit breaks the shape or the ban list")
    args = ap.parse_args()

    rows = [audit(s) for s in framework_slugs()]
    posted = posted_slugs()
    print(render(rows, posted))
    if not args.check:
        return

    # Every unit, published or not. The grandfather clause came out once the
    # whole corpus passed: unlike the grounding check, whose remaining failures
    # are carousels that already dripped and can never be fixed, a unit file is
    # always editable. And these files are the specification — AUTOPRODUCER.md
    # points the hands-off Routine at shipped units and says "match them", so a
    # published unit that breaks the shape teaches the next batch to break it.
    bad = [r for r in rows if not r["ok"]]
    if not bad:
        return
    print("\nNOT CLEAN:")
    for r in bad:
        print(f"  {r['slug']}")
        for p in problems(r):
            print(f"    - {p}")
    print("\nShape: 鐵律二點六 in .claude/skills/x-post/SKILL.md. "
          "Phrases: .claude/skills/renhua/SKILL.md.")
    sys.exit(1)


if __name__ == "__main__":
    main()
