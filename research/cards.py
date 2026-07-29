"""Hypothesis cards — load, validate, and resolve the text a scorer reads.

A card is a Markdown file with YAML front matter in research/hypotheses/. The
front matter is the machine-readable contract; the prose below it is the lab
notebook. Both live in git, which is the mechanism that makes the whole thing
work: the prediction is committed before the data arrives, so a later reading
that happens to fit cannot be passed off as the original one. A model asked to
explain a result will always find an explanation — the timestamp is what
separates a prediction from a story.

Validation is deliberately strict. A card without `min_effect` or `n_per_arm`
is not a hypothesis, it is a hope, and it gets rejected at load time rather
than silently producing a "winner" from three observations.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

import yaml

from research import scorers

BASE = Path(__file__).resolve().parent
HYPOTHESES = BASE / "hypotheses"
UNITS = BASE.parent / "units"

STATUSES = {"open", "testing", "supported", "refuted", "abandoned"}
SOURCES = {"own-metrics", "audience-reply", "external", "intuition"}
METRICS = {"impressions", "engagement_rate", "engagements"}

_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n(.*)\Z", re.S)


@dataclass
class Prediction:
    metric: str
    direction: str                  # e.g. "yes > no"
    min_effect: float               # ratio; below this we call it noise
    n_per_arm: int
    platform: Optional[str] = None  # None = every platform
    block_by: Optional[str] = None
    stop_by: Optional[str] = None

    @property
    def high_arm(self) -> str:
        return self.direction.split(">")[0].strip()

    @property
    def low_arm(self) -> str:
        return self.direction.split(">")[1].strip()


@dataclass
class Hypothesis:
    id: str
    status: str
    source: str
    claim: str
    scorer: str
    prediction: Prediction
    path: Path
    confounds: list[str] = field(default_factory=list)
    body: str = ""
    # Live-experiment wiring, read by research.experiments. Absent on cards that
    # are only ever retro-tested.
    hook_arms: dict = field(default_factory=dict)      # arm -> hook letter
    arm_values: dict = field(default_factory=dict)     # arm -> scorer output

    def score(self, row: dict) -> Optional[str]:
        return scorers.resolve(self.scorer)(row)


def _require(data: dict, key: str, where: str):
    if key not in data:
        raise ValueError(f"{where}: missing required field {key!r}")
    return data[key]


def parse_card(text: str, path: Path) -> Hypothesis:
    m = _FRONT_MATTER.match(text)
    if not m:
        raise ValueError(f"{path.name}: no YAML front matter")
    meta = yaml.safe_load(m.group(1)) or {}
    where = path.name

    status = _require(meta, "status", where)
    if status not in STATUSES:
        raise ValueError(f"{where}: status {status!r} not in {sorted(STATUSES)}")
    source = _require(meta, "source", where)
    if source not in SOURCES:
        raise ValueError(f"{where}: source {source!r} not in {sorted(SOURCES)}")

    var = _require(meta, "variable", where)
    scorer_name = _require(var, "scorer", where)
    scorers.resolve(scorer_name)          # raises on an unknown name

    pred = _require(meta, "prediction", where)
    for key in ("metric", "direction", "min_effect", "n_per_arm"):
        _require(pred, key, f"{where}.prediction")
    if pred["metric"] not in METRICS:
        raise ValueError(f"{where}: metric {pred['metric']!r} not in {sorted(METRICS)}")
    if ">" not in pred["direction"]:
        raise ValueError(f"{where}: direction must read 'high > low'")
    if float(pred["min_effect"]) <= 1.0:
        raise ValueError(
            f"{where}: min_effect must exceed 1.0 — an effect we would not act on "
            "is not worth spending weeks of posting slots to measure"
        )

    return Hypothesis(
        id=_require(meta, "id", where),
        status=status,
        source=source,
        claim=str(_require(meta, "claim", where)).strip(),
        scorer=scorer_name,
        prediction=Prediction(
            metric=pred["metric"],
            direction=pred["direction"],
            min_effect=float(pred["min_effect"]),
            n_per_arm=int(pred["n_per_arm"]),
            platform=pred.get("platform"),
            block_by=pred.get("block_by"),
            stop_by=str(pred["stop_by"]) if pred.get("stop_by") else None,
        ),
        confounds=list(meta.get("confounds") or []),
        path=path,
        body=m.group(2).strip(),
        hook_arms=dict((meta.get("assignment") or {}).get("hook_arms") or {}),
        arm_values=dict((meta.get("assignment") or {}).get("arm_values") or {}),
    )


def load_all(directory: Path = HYPOTHESES) -> list[Hypothesis]:
    return [
        parse_card(p.read_text("utf-8"), p)
        for p in sorted(directory.glob("H-*.md"))
    ]


# ── text resolution ──────────────────────────────────────────────────────────

_HOOK_LINE = re.compile(r"^Hook ([ABC])[^:：]*[:：]\s*(.+)$")
_BODY_LINE = re.compile(r"^Post Body[:：]\s*(.+)$")


def _parse_unit(source: str, hook: str) -> Optional[str]:
    hooks: dict[str, str] = {}
    body: Optional[str] = None
    for line in source.splitlines():
        line = line.strip()
        hm = _HOOK_LINE.match(line)
        if hm:
            hooks[hm.group(1)] = hm.group(2).strip()
            continue
        bm = _BODY_LINE.match(line)
        if bm and body is None:
            body = bm.group(1).strip()
    chosen = hooks.get(hook)
    if chosen is None:
        return None
    return f"{chosen}\n{body}" if body else chosen


@lru_cache(maxsize=None)
def _unit_at(slug: str, as_of: str) -> Optional[str]:
    """The contents of units/<slug>.md as of `as_of`, read out of git history.

    Reading the working-tree file instead would score today's wording against
    results earned by yesterday's. That is not a hypothetical: the units were
    rewritten to lead with provenance on 2026-07-25, after most of the framework
    posts had already gone out, so the current Hook A of bowmans-strategy-clock
    names Cranfield while the version that actually shipped did not. Scoring the
    current file would have put that post in the wrong arm of H-001 — the exact
    hypothesis the rewrite was based on.

    Returns None when git has no version from before that date, which drops the
    row from text-based scoring. Failing closed is the point: an unknown arm is
    recoverable, a confidently wrong one is not.
    """
    rel = f"units/{slug}.md"
    try:
        sha = subprocess.run(
            ["git", "log", "--format=%H", "-1", f"--before={as_of}", "--", rel],
            cwd=BASE.parent, capture_output=True, text=True, timeout=30,
        ).stdout.strip()
        if not sha:
            return None
        out = subprocess.run(
            ["git", "show", f"{sha}:{rel}"],
            cwd=BASE.parent, capture_output=True, text=True, timeout=30,
        )
        return out.stdout if out.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def root_text(slug: str, hook: str, as_of: Optional[str] = None) -> Optional[str]:
    """Rebuild the root post as it went out: the chosen hook, then the opening
    body segment.

    `as_of` is the post's timestamp. Without it this reads the working tree,
    which is only correct for a post that has not gone out yet.
    """
    if as_of:
        source = _unit_at(slug, as_of)
        return _parse_unit(source, hook) if source else None
    path = UNITS / f"{slug}.md"
    return _parse_unit(path.read_text("utf-8"), hook) if path.exists() else None


def hydrate(rows: list[dict]) -> list[dict]:
    """Attach `text` to every row we can rebuild. Rows that keep text=None are
    not scored by text-based scorers — which is the honest outcome, not a bug.

    The durable fix is upstream: the composed root text belongs on the
    Performance row at post time, so no reconstruction is needed at all. Until
    that lands, git history is the best available record of what shipped.
    """
    for row in rows:
        if row.get("text"):
            row.setdefault("text_source", "captured")
            continue
        slug, hook = row.get("slug"), row.get("hook")
        row["text"] = root_text(slug, hook, row.get("posted_at")) if slug and hook else None
        row["text_source"] = "git-history" if row["text"] else None
    return rows
