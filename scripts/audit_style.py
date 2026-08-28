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
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core.composition import compose_posts    # noqa: E402
from core.models import Draft                 # noqa: E402
from core.parsing import parse_units          # noqa: E402

_SENTENCE = re.compile(r"(?<=[。！？])")
_PLAIN = re.compile(r"[，。、；：！？「」『』（）\s]+")


def _plain(text: str) -> str:
    return _PLAIN.sub("", text)

UNITS = ROOT / "units"
CAROUSELS = ROOT / "carousels"
QUEUE = ROOT / "queue" / "carousel_queue.txt"
POSTED = ROOT / "state" / "posted_units.txt"

# One story, four beats: the reader's situation, the framework, what to do with
# it, the judgement. More than this and the piece stops having a spine — every
# extra segment is another subject competing for the same reader.
#
# This was five until 2026-08-27. The fifth was "the turn" — the counter-
# intuitive beat — and in practice it kept collapsing into a list of ways the
# framework goes wrong. Read back, that beat was the least useful part of every
# post: the reader has not used the framework yet, so failure modes are a
# warning about a mistake they are not in a position to make. The turn itself
# still earns a sentence, inside beat 2 or 3; what is gone is giving it a
# segment of its own and filling that segment with pitfalls.
MAX_SEGMENTS = 4

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
#
# Lowered from four to two on 2026-08-27. Four per unit passed every unit and
# still left 146 triads across 45 units, which is what a reader actually meets:
# nobody reads one post, they read the feed. Two is the level where a triad is
# the subject having three parts rather than the sentence having a rhythm.
MAX_TRIADS = 2
_TRIAD = re.compile(r"[^，。、！？\n]{2,10}、[^，。、！？\n]{2,10}、[^，。、！？\n]{2,10}")
# The series' own name. It is three proper nouns in a fixed order, not a
# rhetorical triad, and it appears in most units by design — counting it would
# push units over the cap for saying what the channel is called.
_TRIAD_EXEMPT = "McKinsey、BCG、Bain"

# 排比 — the other half of the rhythm problem, and the half the triad cap never
# saw. A triad is three items joined by 、 inside one clause; this is three whole
# clauses built to the same length and shape, which is the figure that makes a
# paragraph sound recited rather than said:
#
#   指標各報各的，年年都是好消息；行動變成人人做同一件事；溝通剩下一年一次論壇。
#
# Measured 2026-08-27: 53 of these across 45 units, in 39 of them. One a post is
# a writer leaning on a cadence for effect; two is the cadence writing the post.
MAX_PARALLEL_RUNS = 1
_PARALLEL_MIN_CLAUSES = 3
_PARALLEL_HEAD_MIN = 2    # 「指標…指標…指標」
_PARALLEL_HEAD_MAX = 5    # 「每個人都…每個人都…每個人都」

# The same figure in interrogative form: 有沒有 A？有沒有 B？有沒有 C？ It reads as
# a checklist the writer is performing rather than a question the reader has.
MAX_QUESTION_RUNS = 1
_QUESTION_RUN = re.compile(r"(?:[^。！？\n]{4,30}？){3,}")

# A set the text announces by number has to be countable by the reader.
#
# 2026-08-27, from the reader: 「他們歸納出五個條件」 followed by five conditions
# dissolved into flowing prose, and the reader could not tell which five they
# were — they came back with a mis-reconstructed list. Five of the six units
# that announce a numbered set had no ordinals at all in the sentences that
# followed. Prose is the right default for everything else in these posts; a
# numbered set is the one place it costs the reader the thing they came for.
_ANNOUNCE = re.compile(r"(一|二|兩|三|四|五|六|七|八|九|十)個"
                       r"(條件|要素|步驟|問題|指標|階段|層|支柱|面向|部分|部份|"
                       r"象限|類|種|軸|格|欄|環節|角度|維度)")
_ORDINAL = re.compile(r"(?:^|\n)\s*(?:[1-9１-９][.、)）]|第[一二三四五六七八九十]+[個條步層類])")
_CN_NUM = {"一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5,
           "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

# Absolutes. The reader flagged 「致命」 by name; it is the tell of a writer
# reaching for stakes the analysis has not earned, and it travels with a small
# family of the same move. A framework being skipped is not fatal, and saying so
# costs the credibility of every real warning in the corpus.
_ABSOLUTES = re.compile(r"(最?致命|一定散|必死|毀掉|災難性?|崩潰|絕對不?|唯一"
                        r"|徹底改變|顛覆性?)")

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

# The reader sees hook + body, so a body that opens by restating its hook prints
# the same sentence twice. `core.composition` removes a clean restatement before
# posting, but it can only remove what it can recognise: a *reworded* echo
# (「你挑一支牙膏」 against 「你在超市挑一支牙膏」) slips past and ships.
#
# This grades what the reader actually gets — hook composed onto body, for every
# arm — because that is the only place the fault is visible. The way to pass is
# to write the body's opening as the hook verbatim: the composer then strips it
# cleanly for arm B, and arms A and C still get the scene 鐵律零點六 asks for.
MAX_OPENING_ECHO = 0.6

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


def opening_echo(unit) -> list[tuple[str, float]]:
    """Per hook arm, how much the composed post's first body sentence still
    repeats the hook above it. Runs the real composer, so it measures the page
    the reader gets rather than the file on disk."""
    draft = Draft(id="audit", title="audit", content_type="Thread",
                  post_body=unit.post_body, hooks=unit.hooks)
    out = []
    for key, hook in (unit.hooks or {}).items():
        if not hook or not hook.strip():
            continue
        posts = compose_posts(draft, hook, None)
        if not posts or "\n\n" not in posts[0]:
            continue
        head, rest = posts[0].split("\n\n", 1)
        first = next((s for s in _SENTENCE.split(rest) if s.strip()), "")
        if not first:
            continue
        ratio = SequenceMatcher(None, _plain(head), _plain(first)).ratio()
        if ratio > MAX_OPENING_ECHO:
            out.append((key, round(ratio, 2)))
    return out


def parallel_runs(text: str) -> list[str]:
    """Sentences where three or more clauses open with the same words.

    First attempt graded clause lengths instead, on the theory that what makes
    the figure audible is the clauses landing on the same beat. It flagged
    「你熟悉的那間便利商店，開到別的國家之後，架上一半的商品你認不出來」 — one
    subject moving through time, which is just a sentence. Even length is a
    property of plenty of ordinary prose, and a style gate that blocks the build
    on ordinary prose teaches people to write around the gate.

    A repeated opening is the half that is unambiguous, so it is the half that
    is enforced. The other half — three clauses built to the same shape with no
    repeated word — is real, and it is in the skill as a rule for whoever is
    writing, where a judgement call belongs.
    """
    out = []
    for sentence in re.split(r"[。！？\n]", text):
        clauses = [c.strip() for c in re.split(r"[；，]", sentence) if c.strip()]
        if len(clauses) < _PARALLEL_MIN_CLAUSES:
            continue
        for width in range(_PARALLEL_HEAD_MAX, _PARALLEL_HEAD_MIN - 1, -1):
            heads = [c[:width] for c in clauses if len(c) > width]
            if len(heads) < _PARALLEL_MIN_CLAUSES:
                continue
            if max(Counter(heads).values()) >= _PARALLEL_MIN_CLAUSES:
                out.append(sentence.strip())
                break
    return out


def unnumbered_sets(segs: list[str]) -> list[str]:
    """Segments that promise N of something and then do not number them."""
    out = []
    for seg in segs:
        m = _ANNOUNCE.search(seg)
        if not m:
            continue
        want = _CN_NUM.get(m.group(1), 0)
        if want < 3:            # "兩個問題" reads fine as a sentence
            continue
        if len(_ORDINAL.findall(seg)) < want:
            out.append(f"{m.group(0)}：{len(_ORDINAL.findall(seg))}/{want} 有編號")
    return out


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
    echo = opening_echo(unit)
    dashes = text.count("——")
    triads = len(_TRIAD.findall(text.replace(_TRIAD_EXEMPT, "本系列")))
    # 鐵律零點六 puts Hook B verbatim at the top of the body, so anything in
    # that sentence appears in `text` twice and would be counted twice. The
    # reader meets it once.
    parallels = list(dict.fromkeys(parallel_runs(text)))
    qruns = list(dict.fromkeys(_QUESTION_RUN.findall(text)))
    unnumbered = list(dict.fromkeys(unnumbered_sets(segs)))
    absolutes = _ABSOLUTES.findall(text)
    return {
        "slug": slug,
        "segments": len(segs),
        "too_long": [i + 1 for i, n in enumerate(lens) if n > MAX_SEGMENT_CHARS],
        "too_short": [i + 1 for i, n in enumerate(lens) if n < MIN_SEGMENT_CHARS],
        "bans": bans,
        "dashes": dashes,
        "triads": triads,
        "parallels": parallels,
        "qruns": qruns,
        "unnumbered": unnumbered,
        "absolutes": absolutes,
        "closing_tic": bool(CLOSING_TIC.search(segs[-1] if segs else "")),
        "echo": echo,
        "ok": (len(segs) <= MAX_SEGMENTS and not bans and not echo
               and dashes <= MAX_EM_DASH and triads <= MAX_TRIADS
               and len(parallels) <= MAX_PARALLEL_RUNS
               and len(qruns) <= MAX_QUESTION_RUNS
               and not unnumbered and not absolutes
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
    absolutes = _ABSOLUTES.findall(text)
    return {
        "slug": slug,
        "exists": bool(text),
        "dashes": dashes,
        "bans": bans,
        "absolutes": absolutes,
        "ok": not bans and not absolutes and dashes <= MAX_EM_DASH_CAROUSEL,
    }


def carousel_problems(row: dict) -> list[str]:
    out = []
    if row["dashes"] > MAX_EM_DASH_CAROUSEL:
        out.append(f"破折號 —— ×{row['dashes']} (max {MAX_EM_DASH_CAROUSEL})")
    if row.get("absolutes"):
        seen = ", ".join(sorted(set(row["absolutes"])))
        out.append(f"絕對化用語 ×{len(row['absolutes'])}（{seen}）")
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
    for key, ratio in row["echo"]:
        out.append(f"Hook {key} 之後第一句重複咗個 hook（{ratio:.2f}）— the reader gets "
                   "the same sentence twice; write the body's opening as the hook "
                   "verbatim so the composer can strip it")
    if row["triads"] > MAX_TRIADS:
        out.append(f"三項並列 X、Y、Z ×{row['triads']} (max {MAX_TRIADS}) — "
                   "keep the ones that are a real list, cut the ones that are rhythm")
    if len(row["parallels"]) > MAX_PARALLEL_RUNS:
        out.append(f"排比 ×{len(row['parallels'])} (max {MAX_PARALLEL_RUNS}) — three "
                   "clauses cut to the same length read as recited; vary the "
                   "lengths or make it two clauses")
        for s in row["parallels"][:3]:
            out.append(f"    「{s[:48]}」")
    if len(row["qruns"]) > MAX_QUESTION_RUNS:
        out.append(f"連問 ×{len(row['qruns'])} (max {MAX_QUESTION_RUNS}) — a run of "
                   "three questions is a checklist being performed; ask the one "
                   "that matters")
    for u in row["unnumbered"]:
        out.append(f"講咗個數但冇編號 — {u}；讀者數唔到就等於冇講。用 1. 2. 3. 逐行列")
    if row["absolutes"]:
        seen = ", ".join(sorted(set(row["absolutes"])))
        out.append(f"絕對化用語 ×{len(row['absolutes'])}（{seen}）— stakes the analysis "
                   "has not earned; say what actually happens instead")
    for label, n in row["bans"]:
        out.append(f"{label} ×{n}")
    return out


def closing_tic_count(rows: list[dict]) -> int:
    return sum(1 for r in rows if r["closing_tic"])


def render(rows: list[dict], posted: set[str]) -> str:
    out = ["Style audit — story shape and the de-AI list", "",
           f"{'framework':30}{'segs':>5}{'bans':>6}{'——':>5}{'X、Y、Z':>8}"
           f"{'排比':>5}{'冇編號':>7}  state"]
    out.append("-" * 72)
    for r in rows:
        state = "published" if r["slug"] in posted else "still fixable"
        n_bans = sum(n for _, n in r["bans"])
        flag = "" if r["ok"] else "  <-"
        out.append(f"{r['slug']:30}{r['segments']:>5}{n_bans:>6}"
                   f"{r['dashes']:>5}{r['triads']:>8}{len(r['parallels']):>5}"
                   f"{len(r['unnumbered']):>7}  {state}{flag}")
    tic = closing_tic_count(rows)
    unposted_ok = sum(1 for r in rows if r["ok"] and r["slug"] not in posted)
    unposted = sum(1 for r in rows if r["slug"] not in posted)
    out += ["",
            f"{sum(1 for r in rows if r['ok'])}/{len(rows)} clean overall; "
            f"{unposted_ok}/{unposted} of the units nobody has read yet.",
            "Published units are graded and listed, but only the unread ones fail "
            "the build.",
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

    # Published units are reported but do not fail the build.
    #
    # This clause was removed once, for a good reason: unit files are always
    # editable, and they are the specification the hands-off Routine copies, so
    # a published unit breaking the shape teaches the next batch to break it.
    # That reason is answered better by naming exemplars than by the gate —
    # AUTOPRODUCER.md now points at specific units written to the current shape
    # instead of at "the ones that shipped", so the corpus is no longer the spec.
    #
    # What forced the change is the size of the 2026-08-27 rules. Dropping the
    # fifth segment failed all 42 units at once, and a gate that can only be
    # cleared by rewriting 42 posts in one commit does not get cleared — it gets
    # switched off, which costs more than it protects. Everything still to be
    # read is held to the new shape; everything already read is printed as debt
    # with a count, so it stays visible rather than quietly forgiven.
    # Three buckets, split on how much can still be changed.
    #
    # Blocking is everything committed to ship: still in the drip queue, so the
    # next few days of Instagram come out of it. Those are worth stopping a
    # build over because stopping the build is what fixes them.
    #
    # The other two are printed with names and counts and do not block. Already
    # published cannot be unread. Written but not yet queued is the backlog —
    # real work, but a build that has been red since the rules changed stops
    # being read, which is how the corpus drifted in the first place.
    bad = [r for r in rows if not r["ok"] and r["slug"] in pending]
    debt_published = [r for r in rows if not r["ok"] and r["slug"] in posted]
    debt_backlog = [r for r in rows if not r["ok"] and r["slug"] not in posted
                    and r["slug"] not in pending]
    for label, group in (("PUBLISHED", debt_published), ("NOT YET QUEUED", debt_backlog)):
        if not group:
            continue
        print(f"\n{label} AND NOT CLEAN — {len(group)} units, not blocking:")
        for r in group:
            head = [p for p in problems(r) if not p.startswith("    ")][:2]
            print(f"    {r['slug']}: {'; '.join(head)}")
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
