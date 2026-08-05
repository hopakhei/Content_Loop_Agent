#!/usr/bin/env python3
"""Is every post grounded in the reader's own life — on all three channels?

The milkshake post is why this exists. `jobs-to-be-done` opens on somebody
standing in a fast-food doorway counting who buys a milkshake at 7am, and it is
the post readers responded to. The rule that came out of it is in
`.claude/skills/x-post/SKILL.md` as 鐵律零點六: start where the reader stands,
not where the framework came from.

A rule that lives only in a skill file binds whoever happens to read it. Three
channels publish from three different files, on three different crons, and none
of them read a skill at publish time — so this script is the version of the rule
that a machine can apply.

    python scripts/audit_grounding.py            # full table
    python scripts/audit_grounding.py --check    # exit 1 on anything unpublished

`--check` deliberately grades only what has NOT gone out yet: the units whose
drafts are still un-posted and the carousels still in the drip queue. Posts that
already published cannot be fixed, and failing the build over them would make
the check permanent noise — the thing that turns an alarm into wallpaper.
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
from research.scorers import LIFE_NOUNS       # noqa: E402

UNITS = ROOT / "units"
CAROUSELS = ROOT / "carousels"
QUEUE = ROOT / "queue" / "carousel_queue.txt"
LEDGER = ROOT / "state" / "inserted_units.txt"

# The reader has to be in the sentence, as a person, not as "投資者" in the
# third person. 你/妳 is the direct address; 新手 and 初學 name the reader by
# who they are, which the beginner-myth openings use.
READER = ("你", "妳", "新手", "初學")

# An opening that starts on a date is the single most common way this rule gets
# broken — 13 of the first 18 units did it. The window is deliberately narrow:
# a year in the back half of the sentence is provenance, which the rule wants.
_LEAD_YEAR = re.compile(r"^.{0,8}((19|20)\d{2}|\d{2,4}\s*年代)")

# Where a sentence stops being an opening. Chinese full stops plus the dash and
# colon the hooks use to pivot from scene to claim.
_CLAUSE = re.compile(r"[。！？：；]|——")


def opening(text: str) -> str:
    """The first clause — what a Threads reader sees before deciding to scroll."""
    return _CLAUSE.split((text or "").strip(), 1)[0]


def has_life(text: str) -> bool:
    return any(n in (text or "") for n in LIFE_NOUNS)


def grounded_opening(text: str) -> bool:
    """Does this opening stand where the reader stands?

    Two ways to pass: address the reader, or open in a scene they live in.
    One way to fail outright: lead with a date, which puts the framework's
    history first and the reader second.
    """
    head = opening(text)
    if _LEAD_YEAR.match(head):
        return False
    return any(m in head for m in READER) or has_life(head)


# ── channel readers ──────────────────────────────────────────────────────────

def framework_slugs() -> list[str]:
    return sorted(p.stem for p in UNITS.glob("*.md") if not p.stem.isdigit())


def queued() -> list[str]:
    if not QUEUE.exists():
        return []
    return [ln.strip() for ln in QUEUE.read_text("utf-8").splitlines()
            if ln.strip() and not ln.lstrip().startswith("#")]


def audit_unit(slug: str) -> dict:
    """X + Threads. Hooks are the entry point; the body is where the reader
    either recognises their own week or does not."""
    unit = parse_units((UNITS / f"{slug}.md").read_text("utf-8"))[0]
    hooks = {k: (unit.hooks.get(k) or "") for k in "ABC"}
    return {
        "hooks_grounded": {k: grounded_opening(v) for k, v in hooks.items() if v},
        "body_life": has_life(unit.post_body),
    }


def audit_carousel(slug: str) -> dict:
    """Instagram. The cover carries ~80% of the outcome, so it is the entry
    point; the deck and the caption are where the scene has to actually land.

    The cover is graded more loosely than a hook, and on purpose. A cover head
    is two lines of at most seven characters each — demand a life noun inside
    that and you get worse covers, written to satisfy a regex. What it must not
    do is open on a date, and somewhere between head and subtitle the reader or
    their week has to appear.
    """
    path = CAROUSELS / f"{slug}.json"
    if not path.exists():
        return {}
    spec = json.loads(path.read_text("utf-8"))
    slides = spec.get("slides") or [{}]
    cover = slides[0]
    cover_text = " ".join(str(cover.get(k, "")) for k in ("head", "sub")).replace("\n", "")
    deck = " ".join(str(s.get(k, "")) for s in slides for k in ("head", "sub", "body"))
    caption = spec.get("caption", "")
    return {
        "cover_grounded": (not _LEAD_YEAR.match(cover_text)
                           and (any(m in cover_text for m in READER) or has_life(cover_text))),
        "deck_life": has_life(deck),
        # Graded on its first line, not on the whole thing. Instagram truncates
        # a caption at roughly 125 characters behind a "... more" — a 你 in the
        # fourth paragraph is a 你 nobody reads.
        "caption_life": grounded_opening(caption.split("\n")[0]),
    }


def audit(slug: str) -> dict:
    row = {"slug": slug, **audit_unit(slug)}
    row.update(audit_carousel(slug))
    hooks = row.get("hooks_grounded") or {}
    row["ok"] = bool(
        row.get("body_life")
        and row.get("deck_life", True)
        and all(hooks.values())
        and row.get("cover_grounded", True)
    )
    return row


def report() -> list[dict]:
    return [audit(s) for s in framework_slugs()]


def _mark(v) -> str:
    return "—" if v is None else ("ok" if v else "MISS")


def render(rows: list[dict], pending: set[str]) -> str:
    out = [
        "Grounding audit — does the reader appear in their own life, per channel",
        "",
        f"{'framework':30} {'hook A':7}{'hook B':7}{'hook C':7}{'body':6}"
        f"{'cover':7}{'deck':6}{'caption':8} state",
        "-" * 88,
    ]
    for r in rows:
        h = r.get("hooks_grounded") or {}
        state = "queued/unposted" if r["slug"] in pending else "published"
        out.append(
            f"{r['slug']:30} "
            f"{_mark(h.get('A')):7}{_mark(h.get('B')):7}{_mark(h.get('C')):7}"
            f"{_mark(r.get('body_life')):6}"
            f"{_mark(r.get('cover_grounded')):7}{_mark(r.get('deck_life')):6}"
            f"{_mark(r.get('caption_life')):8} {state}"
        )
    bad_pending = [r["slug"] for r in rows if r["slug"] in pending and not r["ok"]]
    bad_live = [r["slug"] for r in rows if r["slug"] not in pending and not r["ok"]]
    out += [
        "",
        f"{sum(1 for r in rows if r['ok'])}/{len(rows)} frameworks fully grounded.",
        f"Not yet published and failing : {len(bad_pending)}"
        + (f" — {', '.join(bad_pending)}" if bad_pending else ""),
        f"Already published and failing : {len(bad_live)} (cannot be fixed, "
        "kept out of --check so the alarm stays meaningful)",
    ]
    return "\n".join(out)


def pending_slugs() -> set[str]:
    """Everything a reader has not seen yet: carousels still in the drip queue,
    and units whose Notion draft has not been created (so not yet posted)."""
    inserted = set()
    if LEDGER.exists():
        inserted = {ln.strip() for ln in LEDGER.read_text("utf-8").splitlines() if ln.strip()}
    return set(queued()) | (set(framework_slugs()) - inserted)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="exit 1 when anything unpublished is not grounded")
    args = ap.parse_args()

    rows = report()
    pending = pending_slugs()
    print(render(rows, pending))
    if not args.check:
        return
    bad = [r for r in rows if r["slug"] in pending and not r["ok"]]
    if bad:
        print("\nNOT GROUNDED (still publishable, so still fixable):")
        for r in bad:
            print(f"  - {r['slug']}")
        print("\nSee 鐵律零點六 in .claude/skills/x-post/SKILL.md. Every post opens "
              "where the reader stands and travels through a scene they live in.")
        sys.exit(1)


if __name__ == "__main__":
    main()
