#!/usr/bin/env python3
"""Retro-test hypothesis cards against posts that already went out.

Most ideas can be killed for free. Every row we have ever posted is in Notion
with its metrics, so a new variable can be scored backwards over the whole
corpus in seconds instead of costing three weeks of posting slots. At one post
a day that difference decides how many questions the account can ever ask.

What this cannot do is close a hypothesis. Retro scoring is observational: the
arms were never randomised, so anything that moved alongside the variable moves
with it in the result. The verdict vocabulary here is therefore separate from
the live one and none of its values is "supported" — the strongest thing a
retro run can say is `retro-supports`, meaning "worth the cost of a real
experiment".

    python scripts/retro_test.py                     # newest snapshot
    python scripts/retro_test.py --card H-001
    python scripts/retro_test.py --live --save research/snapshots/2026-08-01.json

Exit status is 0 whenever the run itself worked, whatever the verdicts say. A
refuted hypothesis is a successful run.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from research import cards, scorers          # noqa: E402

SNAPSHOTS = BASE / "research" / "snapshots"
REPORT = BASE / "research" / "retro_report.md"

BOOTSTRAP_N = 4000
CI = 0.90
SEED = 20260729           # fixed so two runs on one snapshot agree


# ── metrics ──────────────────────────────────────────────────────────────────

def _engagements(row: dict) -> float:
    return (row.get("likes") or 0) + (row.get("replies") or 0) + (row.get("reposts") or 0)


def metric_value(row: dict, metric: str) -> Optional[float]:
    impr = row.get("impressions")
    if not impr or impr <= 0:
        # None is "never measured", 0 is a failed fetch stored as zero. Neither
        # is a measurement, and a rate cannot be formed from either.
        return None
    if metric == "impressions":
        return float(impr)
    if metric == "engagements":
        return _engagements(row)
    if metric == "engagement_rate":
        return _engagements(row) / float(impr)
    raise ValueError(f"unknown metric {metric!r}")


# ── statistics ───────────────────────────────────────────────────────────────

def bootstrap_ratio(high: list[float], low: list[float]) -> tuple[float, float, float]:
    """Point estimate and CI for mean(high)/mean(low), by resampling.

    A ratio rather than a difference because the interesting effects here span
    orders of magnitude (40 impressions against 19,000), and because min_effect
    on a card is written as a multiple. Bootstrapping rather than a t-test
    because these distributions are visibly skewed — one post in the corpus
    carries 19,115 impressions against a median near 600 — and no amount of
    small-sample theory fixes that.
    """
    rng = random.Random(SEED)
    point = statistics.fmean(high) / statistics.fmean(low)
    draws = []
    for _ in range(BOOTSTRAP_N):
        h = statistics.fmean(rng.choices(high, k=len(high)))
        lo = statistics.fmean(rng.choices(low, k=len(low)))
        if lo > 0:
            draws.append(h / lo)
    if not draws:
        return point, float("nan"), float("nan")
    draws.sort()
    tail = (1 - CI) / 2
    return point, draws[int(tail * len(draws))], draws[int((1 - tail) * len(draws)) - 1]


# ── confound detection ───────────────────────────────────────────────────────

def _dates(rows: list[dict]) -> tuple[Optional[datetime], Optional[datetime]]:
    stamps = []
    for r in rows:
        raw = r.get("posted_at")
        if raw:
            stamps.append(datetime.fromisoformat(raw.replace("Z", "+00:00")))
    return (min(stamps), max(stamps)) if stamps else (None, None)


def concurrency_warning(arms: dict[str, list[dict]]) -> Optional[str]:
    """Flag arms that did not run at the same time.

    This is the check the old X link A/B needed and never had. Its `link` arm
    stopped being assigned on 2026-07-19 while `no_link` kept running into a
    period when the account's reach changed by an order of magnitude, and the
    nightly digest went on reporting the two as a live comparison.
    """
    windows = {a: _dates(rs) for a, rs in arms.items() if rs}
    if len(windows) < 2:
        return None
    starts = [w[0] for w in windows.values() if w[0]]
    ends = [w[1] for w in windows.values() if w[1]]
    if not starts or not ends:
        return None
    overlap = (min(ends) - max(starts)).total_seconds()
    union = (max(ends) - min(starts)).total_seconds()
    if union <= 0:
        return None
    share = max(0.0, overlap) / union
    if share >= 0.6:
        return None
    spans = "; ".join(
        f"{a}: {w[0]:%Y-%m-%d}..{w[1]:%Y-%m-%d}" for a, w in sorted(windows.items())
    )
    return (
        f"arms overlap in time for only {share:.0%} of the span ({spans}) — "
        "anything that changed on the account between those windows is in the result"
    )


def era_warning(arms: dict[str, list[dict]]) -> Optional[str]:
    """Flag arms that sit on opposite sides of the numbered/framework split."""
    mix = {
        arm: {scorers.series_era(r) for r in rows}
        for arm, rows in arms.items() if rows
    }
    if len(mix) < 2:
        return None
    if all(len(eras) == 1 for eras in mix.values()) and len({next(iter(e)) for e in mix.values()}) > 1:
        detail = ", ".join(f"{a}={next(iter(e))}" for a, e in sorted(mix.items()))
        return f"each arm sits entirely in one content era ({detail}) — the eras differ in everything, not just this variable"
    return None


# ── the run ──────────────────────────────────────────────────────────────────

def evaluate(h: cards.Hypothesis, rows: list[dict]) -> dict:
    pool = [r for r in rows if not h.prediction.platform or r.get("platform") == h.prediction.platform]

    arms: dict[str, list[dict]] = {}
    for row in pool:
        arm = h.score(row)
        if arm is None:
            continue
        arms.setdefault(str(arm), []).append(row)

    measured = {
        arm: [v for v in (metric_value(r, h.prediction.metric) for r in rs) if v is not None]
        for arm, rs in arms.items()
    }
    measured = {a: v for a, v in measured.items() if v}

    result = {
        "id": h.id,
        "claim": h.claim,
        "scorer": h.scorer,
        "metric": h.prediction.metric,
        "platform": h.prediction.platform or "all",
        "scored": sum(len(v) for v in arms.values()),
        "arms": {
            a: {"n": len(v), "mean": statistics.fmean(v)} for a, v in sorted(measured.items())
        },
        "warnings": [w for w in (
            concurrency_warning({a: arms[a] for a in measured}),
            era_warning({a: arms[a] for a in measured}),
        ) if w],
        "verdict": "no-variation",
        "detail": "",
    }

    hi, lo = h.prediction.high_arm, h.prediction.low_arm
    if hi not in measured or lo not in measured:
        present = sorted(measured) or ["none"]
        result["detail"] = (
            f"needs arms {hi!r} and {lo!r}; the corpus only has {present}. "
            "Every post in range took the same value, so there is nothing to compare."
        )
        return result

    point, low_ci, high_ci = bootstrap_ratio(measured[hi], measured[lo])
    result["ratio"] = point
    result["ci"] = [low_ci, high_ci]

    thin = min(len(measured[hi]), len(measured[lo])) < h.prediction.n_per_arm
    excludes_one = low_ci > 1.0 or high_ci < 1.0

    if thin:
        result["verdict"] = "still-thin"
        result["detail"] = (
            f"{hi} n={len(measured[hi])}, {lo} n={len(measured[lo])}; the card asks for "
            f"{h.prediction.n_per_arm} per arm before anything is read off this."
        )
    elif not excludes_one:
        result["verdict"] = "inconclusive"
        result["detail"] = f"90% CI [{low_ci:.2f}, {high_ci:.2f}] contains 1.0 — no direction established."
    elif point < h.prediction.min_effect:
        result["verdict"] = "below-min-effect"
        result["detail"] = (
            f"{point:.2f}x is real but under the {h.prediction.min_effect}x the card "
            "committed to acting on."
        )
    else:
        result["verdict"] = "retro-supports"
        result["detail"] = (
            f"{point:.2f}x, 90% CI [{low_ci:.2f}, {high_ci:.2f}]. Observational — "
            "worth a randomised run, not a rule yet."
        )
    return result


def load_rows(args) -> tuple[list[dict], str]:
    if args.live:
        from services.notion import NotionService     # noqa: PLC0415 — optional dep path
        rows = NotionService().get_performance_rows(since_days=args.since_days)
        for r in rows:
            r.setdefault("hook", (r.get("hook_used") or "")[:1] or None)
            r["slug"] = r.get("slug")
        payload = {
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": "notion-live",
            "rows": rows,
        }
        if args.save:
            Path(args.save).write_text(
                json.dumps(payload, ensure_ascii=False, indent=1) + "\n", "utf-8")
        return rows, "notion-live"

    path = Path(args.snapshot) if args.snapshot else max(
        SNAPSHOTS.glob("*.json"), key=lambda p: p.name, default=None)
    if not path:
        sys.exit("no snapshot in research/snapshots/ — run once with --live --save")
    data = json.loads(path.read_text("utf-8"))
    return data["rows"], path.name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--snapshot", help="snapshot JSON (default: newest by name)")
    ap.add_argument("--live", action="store_true", help="read Notion instead of a snapshot")
    ap.add_argument("--save", help="with --live, write the rows to this path")
    ap.add_argument("--since-days", type=int, default=120)
    ap.add_argument("--card", action="append", help="only these ids (repeatable)")
    args = ap.parse_args()

    rows, origin = load_rows(args)
    cards.hydrate(rows)

    hypotheses = cards.load_all()
    if args.card:
        wanted = set(args.card)
        hypotheses = [h for h in hypotheses if h.id in wanted]
    if not hypotheses:
        sys.exit("no hypothesis cards matched")

    results = [evaluate(h, rows) for h in hypotheses]

    lines = [
        "# Retro report",
        "",
        f"_Generated by `scripts/retro_test.py` from **{origin}** ({len(rows)} rows). "
        "Observational: no arm here was randomised, so the strongest available verdict "
        "is `retro-supports`, which means the hypothesis has earned a real experiment._",
        "",
    ]
    for r in results:
        lines += [
            f"## {r['id']} — {r['verdict']}",
            "",
            f"{r['claim']}",
            "",
            f"- variable: `{r['scorer']}` | metric: `{r['metric']}` | platform: {r['platform']}",
            f"- rows scored: {r['scored']}",
        ]
        for arm, s in r["arms"].items():
            lines.append(f"- **{arm}**: n={s['n']}, mean {s['mean']:,.4g}")
        if "ratio" in r:
            lo, hi = r["ci"]
            lines.append(f"- ratio: {r['ratio']:.2f}x, 90% CI [{lo:.2f}, {hi:.2f}]")
        if r["detail"]:
            lines.append(f"- {r['detail']}")
        for w in r["warnings"]:
            lines.append(f"- ⚠️ **confound**: {w}")
        lines.append("")

    report = "\n".join(lines)
    REPORT.write_text(report, "utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
