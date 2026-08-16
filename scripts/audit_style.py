#!/usr/bin/env python3
"""Two things a reader feels immediately and no test was watching.

**Shape.** A framework unit is one story, not an inventory of everything known
about the framework. The batch drifted to nine segments — origin, mechanism,
mechanism, scene, error, approach, investor angle, caveat, close — nine
subjects with no spine, which reads as a list even when every line is true.

**Plain language.** 鐵律零點七 sets the bar: explain it the way you would to a
six-year-old. Consultant shorthand with a plain equivalent is banned outright;
the terms the series actually teaches are not, because those have to be glossed
rather than avoided, and no checker can tell the difference.

**The de-AI list.** `.claude/skills/renhua/SKILL.md` bans a specific set of
phrases. The de-AI pass has been catching the loud half (真正, 其實, 先別) and
missing the common half: at the time this was written the corpus held 33 uses
of 東西 and 19 of 這件事, the two vague-referent bans, against a single 其實.
A rule enforced by whoever remembers it is enforced on the memorable clauses.

**Tics, not words.** The owner read the batch and said the AI flavour was still
heavy. Every unit passed the ban list, so the problem was a level up: the same
*move*, repeated. Measured 2026-08-16 across 34 units — 149 em-dashes (median 4
a post, worst 9), 126 three-item enumerations (worst 10), and 31 of 34 posts
ending on the identical "下一個框架是 X：Y". None of that is catchable one
sentence at a time, which is why it survived every previous pass. Two of the
three are per-unit caps; the closing is a corpus-level count, because a single
post ending that way is a style and thirty-one is a template.

    python scripts/audit_style.py            # full table
    python scripts/audit_style.py --check    # exit 1 on any unit

Unlike the grounding audit, this one has no grandfather clause: a unit file is
always editable, and it doubles as the specification the auto-producer copies
when AUTOPRODUCER.md tells it to read two shipped units and match them.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.parsing import parse_units          # noqa: E402

UNITS = ROOT / "units"
CAROUSELS = ROOT / "carousels"
QUEUE = ROOT / "queue" / "carousel_queue.txt"
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

# The em-dash pivot: a judgement, then —— , then a dramatic elaboration. One a
# post is punctuation; four is a habit the reader hears. Both public de-AI
# skills flag it independently (shyuan/writing-humanizer 模式 13,
# op7418/Humanizer-zh #13), and it was the single densest tic in the corpus.
MAX_EM_DASH = 2

# Rhetorical triads — "X、Y、Z" as a rhythm rather than as a real list. The
# cap is deliberately not a ban: a framework with five parts gets to name five
# parts, so upstream's "rewrite every triad as two or four items" would cut
# into the subject matter. Four separate enumerations in an 850-character post
# is already more than any of them is earning.
MAX_TRIADS = 4
_TRIAD = re.compile(r"[^，。、！？\n]{2,10}、[^，。、！？\n]{2,10}、[^，。、！？\n]{2,10}")
# The series' own name. It is three proper nouns in a fixed order, not a
# rhetorical triad, and it appears in most units by design — counting it would
# push units over the cap for saying what the channel is called.
_TRIAD_EXEMPT = "McKinsey、BCG、Bain"

# Corpus-level. Handing off to the next framework is a real series device and
# it stays; what does not stay is every post making the handoff with the same
# sentence. The ceiling is roughly six in ten, which leaves the device intact
# and forces the rest to close on a fact, a judgement, or something the reader
# can do tonight.
CLOSING_TIC = re.compile(r"下一個框架")
MAX_CLOSING_TIC = 20

# Instagram was never graded by this script, and it turned out to be where the
# tic was densest: 236 em-dashes across the deck files against 149 in the
# units, plus jargon (對沖, 敏感度分析) that the unit ban list would have
# rejected outright. A deck plus its caption runs roughly three times the text
# of a unit, so the cap is scaled rather than copied.
MAX_EM_DASH_CAROUSEL = 4

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

# Consultant and finance shorthand with a plain equivalent, banned outright.
#
# The standard is the owner's, verbatim: explain it the way you would to a
# six-year-old. Every term here has a plain replacement listed in 鐵律零點七,
# and none of them is the subject of a framework — so there is never a reason
# to spend the reader's attention on decoding one.
#
# Terms the series actually teaches (護城河, 毛利率, 損益表, 議價能力, 本益比,
# 客戶終身價值) are deliberately NOT here. They cannot be banned; the rule for
# them is to gloss them in plain words on first use, and no checker can verify
# that. This list covers only the part a machine can be trusted with.
JARGON: list[tuple[str, re.Pattern]] = [
    ("顧問行話「基點」", re.compile(r"基點")),
    ("顧問行話「ROIC / 投入資本報酬」", re.compile(r"ROIC|投入資本報酬")),
    ("顧問行話「EBITDA」", re.compile(r"EBITDA")),
    ("顧問行話「綜效」", re.compile(r"綜效")),
    ("顧問行話「資產減損」", re.compile(r"資產減損")),
    ("顧問行話「資本密集度」", re.compile(r"資本密集")),
    ("顧問行話「現金轉換循環」", re.compile(r"現金轉換循環")),
    ("顧問行話「營運資金是負數」", re.compile(r"營運資金是負")),
    ("顧問行話「對沖」", re.compile(r"對沖")),
    ("顧問行話「敏感度分析」", re.compile(r"敏感度分析")),
    ("顧問行話「decision-grade」", re.compile(r"decision-grade")),
    ("顧問行話「開刀 / 第一刀」", re.compile(r"開刀|第一刀")),
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
    for label, rx in BANS + JARGON:
        found = rx.findall(text)
        if found:
            bans.append((label, len(found)))

    lens = [len(s) for s in segs]
    dashes = text.count("——")
    triads = len(_TRIAD.findall(text.replace(_TRIAD_EXEMPT, "本系列")))
    return {
        "slug": slug,
        "segments": len(segs),
        "too_long": [i + 1 for i, n in enumerate(lens) if n > MAX_SEGMENT_CHARS],
        "too_short": [i + 1 for i, n in enumerate(lens) if n < MIN_SEGMENT_CHARS],
        "bans": bans,
        "dashes": dashes,
        "triads": triads,
        "closing_tic": bool(CLOSING_TIC.search(segs[-1] if segs else "")),
        "ok": (len(segs) <= MAX_SEGMENTS and not bans
               and dashes <= MAX_EM_DASH and triads <= MAX_TRIADS
               and all(MIN_SEGMENT_CHARS <= n <= MAX_SEGMENT_CHARS for n in lens)),
    }


def queued() -> list[str]:
    """Carousels a reader has not seen yet. Same source of truth the grounding
    audit uses, and the same reason: a deck that already dripped cannot be
    fixed, so failing the build over it would train everyone to ignore the
    alarm. The file still gets graded and printed — it just does not gate."""
    if not QUEUE.exists():
        return []
    return [ln.strip() for ln in QUEUE.read_text("utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def carousel_text(slug: str) -> str:
    """Everything a reader actually reads: the caption plus every slide's
    kicker, head, subtitle and body."""
    path = CAROUSELS / f"{slug}.json"
    if not path.exists():
        return ""
    spec = json.loads(path.read_text("utf-8"))
    parts = [spec.get("caption", "")]
    for slide in spec.get("slides", []):
        parts += [str(slide.get(k, "")) for k in ("kicker", "head", "sub", "body")]
    return "\n".join(p for p in parts if p)


def audit_carousel(slug: str) -> dict:
    text = carousel_text(slug)
    bans = []
    for label, rx in BANS + JARGON:
        found = rx.findall(text)
        if found:
            bans.append((label, len(found)))
    dashes = text.count("——")
    return {
        "slug": slug,
        "exists": bool(text),
        "dashes": dashes,
        "bans": bans,
        "ok": not bans and dashes <= MAX_EM_DASH_CAROUSEL,
    }


def carousel_problems(row: dict) -> list[str]:
    out = []
    if row["dashes"] > MAX_EM_DASH_CAROUSEL:
        out.append(f"破折號 —— ×{row['dashes']} (max {MAX_EM_DASH_CAROUSEL})")
    for label, n in row["bans"]:
        out.append(f"{label} ×{n}")
    return out


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
    if row["dashes"] > MAX_EM_DASH:
        out.append(f"破折號 —— ×{row['dashes']} (max {MAX_EM_DASH}) — the pivot "
                   "move; swap for a comma, a full stop, or two sentences")
    if row["triads"] > MAX_TRIADS:
        out.append(f"三項並列 X、Y、Z ×{row['triads']} (max {MAX_TRIADS}) — "
                   "keep the ones that are a real list, cut the ones that are rhythm")
    for label, n in row["bans"]:
        out.append(f"{label} ×{n}")
    return out


def closing_tic_count(rows: list[dict]) -> int:
    return sum(1 for r in rows if r["closing_tic"])


def render(rows: list[dict], posted: set[str]) -> str:
    out = ["Style audit — story shape and the de-AI list", "",
           f"{'framework':30}{'segs':>5}{'bans':>6}{'——':>5}{'X、Y、Z':>8}  state"]
    out.append("-" * 72)
    for r in rows:
        state = "published" if r["slug"] in posted else "still fixable"
        n_bans = sum(n for _, n in r["bans"])
        flag = "" if r["ok"] else "  <-"
        out.append(f"{r['slug']:30}{r['segments']:>5}{n_bans:>6}"
                   f"{r['dashes']:>5}{r['triads']:>8}  {state}{flag}")
    tic = closing_tic_count(rows)
    out += ["",
            f"{sum(1 for r in rows if r['ok'])}/{len(rows)} clean. "
            "The state column is context, not an exemption — every unit is graded.",
            f"Closing handoff「下一個框架」: {tic}/{len(rows)} "
            f"(max {MAX_CLOSING_TIC}) — a corpus-level tic, invisible one post at a time."]
    return "\n".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 when any unit breaks the shape or the ban list")
    args = ap.parse_args()

    rows = [audit(s) for s in framework_slugs()]
    posted = posted_slugs()
    print(render(rows, posted))

    pending = set(queued())
    decks = [audit_carousel(s) for s in framework_slugs()]
    decks = [d for d in decks if d["exists"]]
    bad_decks = [d for d in decks if not d["ok"]]
    print(f"\nInstagram decks: {sum(1 for d in decks if d['ok'])}/{len(decks)} clean "
          f"({sum(1 for d in bad_decks if d['slug'] in pending)} of them still in the "
          "drip queue and therefore fixable).")
    if not args.check:
        return

    # Every unit, published or not. The grandfather clause came out once the
    # whole corpus passed: unlike the grounding check, whose remaining failures
    # are carousels that already dripped and can never be fixed, a unit file is
    # always editable. And these files are the specification — AUTOPRODUCER.md
    # points the hands-off Routine at shipped units and says "match them", so a
    # published unit that breaks the shape teaches the next batch to break it.
    bad = [r for r in rows if not r["ok"]]
    tic = closing_tic_count(rows)
    bad_queued = [d for d in bad_decks if d["slug"] in pending]
    if not bad and not bad_queued and tic <= MAX_CLOSING_TIC:
        return
    if bad_queued:
        print("\nDECKS NOT CLEAN (still in the queue, so still fixable):")
        for d in bad_queued:
            print(f"  carousels/{d['slug']}.json")
            for p in carousel_problems(d):
                print(f"    - {p}")
    if bad:
        print("\nNOT CLEAN:")
        for r in bad:
            print(f"  {r['slug']}")
            for p in problems(r):
                print(f"    - {p}")
    if tic > MAX_CLOSING_TIC:
        print(f"\nCORPUS-LEVEL: {tic} of {len(rows)} units close on 「下一個框架」 "
              f"(max {MAX_CLOSING_TIC}).")
        print("  Every one of them reads fine alone. Read five in a row and it is a "
              "template.\n  Keep the handoff where it earns its place — move it into "
              "the middle of the\n  last segment, or close on a fact, a judgement, or "
              "something the reader can do\n  tonight, and let the next framework be a "
              "surprise.")
        for r in rows:
            if r["closing_tic"]:
                print(f"    - {r['slug']}")
    print("\nShape: 鐵律二點六 in .claude/skills/x-post/SKILL.md. "
          "Phrases: .claude/skills/renhua/SKILL.md. "
          "Tics: 篇級 in .claude/skills/content-anti-ai/SKILL.md.")
    sys.exit(1)


if __name__ == "__main__":
    main()
