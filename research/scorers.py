"""Scorers — pure functions that turn a posted row into one variable's value.

A hypothesis names a scorer; the scorer decides which arm a row belongs to.
That is the whole point of this module: adding a variable to the experiment
substrate is a function here plus a card in research/hypotheses/, with no edit
to core/tagging.py and no new Notion property. The old arrangement hard-coded
eight tag keys in `build_tags()`, so the set of questions the system could ever
ask was fixed by whoever wrote that dict.

Contract, borrowed from `core.analysis.ranked_by_tag`: return None when the row
cannot be scored. None means "unknown", never "no" — a row we cannot classify is
dropped from the comparison rather than quietly stuffed into the negative arm.

Everything here is a pure function of the row dict. No I/O, no imports from
services/, so the maths stays testable without a network.
"""
from __future__ import annotations

import re
from typing import Callable, Optional

Scorer = Callable[[dict], Optional[str]]


# ── helpers ──────────────────────────────────────────────────────────────────

def first_line(row: dict) -> Optional[str]:
    """The opening line as a reader sees it. Threads truncates its feed preview
    after a couple of lines, so this is the only text most people ever get."""
    text = (row.get("text") or "").strip()
    if not text:
        return None
    return text.splitlines()[0].strip() or None


# The two provenance layers the x-post skill keeps apart, and for the same
# reason: naming the firms is a claim about who uses the framework, naming the
# author is a claim about who wrote it. A hypothesis about "authority" that
# conflated them would be untestable, because a refutation could always be
# explained away as the wrong kind of authority.
FIRMS = ("McKinsey", "麥肯錫", "BCG", "Bain", "波士頓顧問")
AUTHORS = (
    "Porter", "Christensen", "Ansoff", "Bowman", "Henderson", "Faulkner",
    "Hunt", "Kim", "Mauborgne", "INSEAD", "Harvard", "哈佛", "Cranfield",
    "商學院", "《哈佛商業評論》",
)
CONSULTANTS = ("策略顧問", "顧問")

_YEAR = re.compile(r"(19|20)\d{2}")
_DIGIT = re.compile(r"\d")

# Nouns that put the reader's own position in the frame — their holding, its
# margin, its valuation — as opposed to an opening that starts on a scene.
INVESTOR_NOUNS = (
    "公司", "股", "毛利", "估值", "買", "財報", "年報", "管理層", "行業",
    "護城河", "利潤", "賺", "成本", "增長", "股價", "同業", "現金",
)


def _any(haystack: Optional[str], needles) -> bool:
    return bool(haystack) and any(n in haystack for n in needles)


# ── scorers ──────────────────────────────────────────────────────────────────

def authority_line1(row: dict) -> Optional[str]:
    """Does the opening line name a recognisable firm, author or institution?"""
    line = first_line(row)
    if line is None:
        return None
    return "yes" if _any(line, FIRMS + AUTHORS + CONSULTANTS) else "no"


def firm_name_line1(row: dict) -> Optional[str]:
    """Narrower: the consulting trio specifically, not the framework's author."""
    line = first_line(row)
    if line is None:
        return None
    return "yes" if _any(line, FIRMS) else "no"


def authority_anywhere(row: dict) -> Optional[str]:
    """Control for `authority_line1`: provenance present, but possibly below the
    fold. If the line-1 effect is real, these two must not move together."""
    text = row.get("text")
    if not text:
        return None
    return "yes" if _any(text, FIRMS + AUTHORS + CONSULTANTS) else "no"


def investor_opener(row: dict) -> Optional[str]:
    """Does line 1 talk about the reader's own holding, or open on a scene?"""
    line = first_line(row)
    if line is None:
        return None
    return "yes" if _any(line, INVESTOR_NOUNS) else "no"


def number_in_line1(row: dict) -> Optional[str]:
    line = first_line(row)
    if line is None:
        return None
    return "yes" if _DIGIT.search(line) else "no"


def year_in_line1(row: dict) -> Optional[str]:
    line = first_line(row)
    if line is None:
        return None
    return "yes" if _YEAR.search(line) else "no"


def line1_len_bucket(row: dict) -> Optional[str]:
    line = first_line(row)
    if line is None:
        return None
    n = len(line)
    return "short" if n <= 20 else ("mid" if n <= 40 else "long")


def hook_label(row: dict) -> Optional[str]:
    return row.get("hook") or None


def x_link_arm(row: dict) -> Optional[str]:
    """The one variable that was already randomised, read back off the tag."""
    return (row.get("tags") or {}).get("x_link_arm")


# Scenes from ordinary life, as opposed to boardrooms and balance sheets. The
# list is the operational definition of "貼地" for H-005: a post is life-anchored
# when its text puts the reader somewhere they actually stand in a normal week.
# Editing this list after H-005 goes live would move posts between arms
# retroactively — treat it as frozen while the card is in `testing`.
LIFE_NOUNS = (
    "奶昔", "早餐", "咖啡", "通勤", "排隊", "餐廳", "茶餐廳", "超市", "便利商店",
    "外送", "菜市場", "夜市", "衣櫃", "行李", "房租", "水電", "手機", "追劇",
    "健身房", "捷運", "公車", "計程車", "巷口", "樓下", "週末", "下班", "加班",
    "薪水", "帳單", "團購", "網購", "遊戲", "理髮", "洗衣",
)


def life_anchor(row: dict) -> Optional[str]:
    """Does the post text ground its argument in an everyday scene?

    Full-text, not line 1: H-002 already owns the opening line, and this
    variable is about whether the argument itself travels through a scene the
    reader lives in (the JTBD milkshake) or stays inside the boardroom (the
    GE capital-allocation table). A post can be investor-opened and still
    life-anchored — the two variables are deliberately independent.
    """
    text = row.get("text")
    if not text:
        return None
    return "yes" if _any(text, LIFE_NOUNS) else "no"


def series_era(row: dict) -> Optional[str]:
    """Numbered-essay era vs framework-series era.

    Not a lever anyone can pull per post — it is the single biggest thing that
    changed in this account's history, so every other comparison has to be
    checked against it before it means anything.
    """
    return "framework" if row.get("slug") else "numbered"


REGISTRY: dict[str, Scorer] = {
    "authority_line1": authority_line1,
    "firm_name_line1": firm_name_line1,
    "authority_anywhere": authority_anywhere,
    "investor_opener": investor_opener,
    "number_in_line1": number_in_line1,
    "year_in_line1": year_in_line1,
    "line1_len_bucket": line1_len_bucket,
    "hook_label": hook_label,
    "x_link_arm": x_link_arm,
    "life_anchor": life_anchor,
    "series_era": series_era,
}


def resolve(name: str) -> Scorer:
    try:
        return REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"unknown scorer {name!r}; known: {sorted(REGISTRY)}"
        ) from None
