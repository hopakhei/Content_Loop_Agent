"""Every framework must exist on all three platforms, not just one.

A framework carousel feeds Instagram; a framework unit feeds X and Threads.
They are separate content sources with no code path linking them, so building
one and forgetting the other is silent — the missing feed simply goes quiet.
That happened: ten carousels shipped while units/ still held two frameworks,
Notion ran out of framework drafts, and Loop 1 posted nothing to X or Threads
for a day before anyone noticed.

These tests make the omission loud at commit time instead.
"""
from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
QUERIES = BASE / "assets" / "background_queries.json"


def _framework_slugs(directory: str, suffix: str) -> set[str]:
    """Slugs in `directory` that name a framework — numeric ones are the
    per-article series (101-201, 127), which follow a different pipeline."""
    return {
        p.name[: -len(suffix)]
        for p in (BASE / directory).glob(f"*{suffix}")
        if not p.name[: -len(suffix)].isdigit()
    }


def test_every_framework_carousel_has_a_unit():
    """Instagram has it, so X and Threads must too."""
    missing = _framework_slugs("carousels", ".json") - _framework_slugs("units", ".md")
    assert not missing, (
        f"carousel(s) with no units/<slug>.md: {sorted(missing)} — X and Threads "
        "would run dry. Write the flagship Thread unit before shipping the carousel."
    )


def test_every_framework_unit_has_a_carousel():
    """X and Threads have it, so Instagram must too."""
    missing = _framework_slugs("units", ".md") - _framework_slugs("carousels", ".json")
    assert not missing, (
        f"unit(s) with no carousels/<slug>.json: {sorted(missing)} — Instagram "
        "would skip this framework entirely."
    )


def test_every_framework_carousel_has_background_queries():
    """No queries means no photos, and the slides fall back to line art."""
    queries = {k for k in json.loads(QUERIES.read_text("utf-8")) if not k.startswith("_")}
    missing = _framework_slugs("carousels", ".json") - queries
    assert not missing, (
        f"carousel(s) absent from assets/background_queries.json: {sorted(missing)}"
    )


def test_background_queries_cover_every_slide():
    """A per-slide list has to line up with the spec, or later slides silently
    lose their picture while earlier ones keep theirs."""
    queries = {k: v for k, v in json.loads(QUERIES.read_text("utf-8")).items()
               if not k.startswith("_")}
    for slug, spec in queries.items():
        if not isinstance(spec, list):
            continue                      # cover-only form is allowed
        path = BASE / "carousels" / f"{slug}.json"
        if not path.exists():
            continue                      # covered by the test above
        slides = len(json.loads(path.read_text("utf-8"))["slides"])
        assert len(spec) == slides, (
            f"{slug}: {len(spec)} queries for {slides} slides"
        )


def test_caption_keywords_are_wired_to_the_dm_bot():
    """A caption asking for a word the bot does not answer is a dead CTA.

    This shipped: twenty framework captions asked readers to comment 「框架」
    while IG_DM_KEYWORD was still the single value 「全文」, so every one of
    those comments went unanswered and nobody could tell from the outside.
    """
    import re
    from config import settings

    known = {k.casefold() for k in settings.IG_DM_KEYWORDS}
    asked: set[str] = set()
    for path in (BASE / "carousels").glob("*.json"):
        spec = json.loads(path.read_text("utf-8"))
        blob = spec.get("caption", "") + " ".join(
            s.get("follow", "") for s in spec["slides"]
        )
        asked |= set(re.findall(r"留言「([^」]+)」", blob))

    unanswered = {w for w in asked if w.casefold() not in known}
    assert not unanswered, (
        f"caption(s) ask for {sorted(unanswered)} but IG_DM_KEYWORD only answers "
        f"{sorted(known)} — those comments get no DM."
    )
