"""The live half of the research loop: assign arms at post time.

One experiment runs at a time. That is not caution, it is arithmetic — at one
post a day a two-arm test on Threads collects about 15 rows per arm per month,
and two concurrent experiments would quarter every cell and settle nothing. The
registry refuses to load a second card in `testing`.

Assignment is a fair coin seeded by (experiment, draft, day), so a re-run of the
same slot lands on the same arm while the same framework posted later can land
on the other one. It is deliberately not adaptive: an allocation that chases the
current leader stops being a randomised test and becomes the same
leaderboard-following the learn loop already does.

Fail closed. If the arm a coin picks cannot actually be produced for this draft
— the hook it needs is missing, or the hook does not score the way the card says
it should — the post goes out on the normal path and is recorded as unassigned.
A post filed under an arm it was not really in is worse than no data.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from typing import Optional

from research import cards, scorers


@dataclass
class Assignment:
    experiment: str          # card id, e.g. "H-002"
    arm: str                 # e.g. "scene"
    hook_key: Optional[str]  # hook the arm requires, when it names one

    @property
    def tag(self) -> dict:
        return {f"{self.experiment.lower().replace('-', '')}_arm": self.arm}


def active(hypotheses: Optional[list[cards.Hypothesis]] = None) -> Optional[cards.Hypothesis]:
    """The single card in `testing`, or None."""
    live = [h for h in (hypotheses or cards.load_all()) if h.status == "testing"]
    if len(live) > 1:
        raise ValueError(
            "more than one hypothesis is in `testing` "
            f"({', '.join(h.id for h in live)}) — at one post a day that splits "
            "every cell below the point where either can be read"
        )
    return live[0] if live else None


def _coin(draft_id: str, experiment: str, day: str) -> int:
    """Deterministic fair coin over (experiment, draft, day).

    The day has to be in there. Seeding on the draft alone would pin each
    framework to one arm for the life of the experiment, so "investor vs scene"
    would also be "these seven frameworks vs those three" — framework identity
    is the largest source of variance on this account, and that is precisely the
    confound blocking is supposed to remove. With the day included, a framework
    reposted later can land on the other side, and each one contributes to both
    arms over the run.

    Within a day it stays fixed, which is all the determinism a retried slot
    needs: a re-run cannot move a post from one arm to the other.
    """
    digest = hashlib.sha256(f"{experiment}:{draft_id}:{day}".encode()).digest()
    return digest[0] & 1


def assign(
    draft,
    platform: str,
    hypothesis: Optional[cards.Hypothesis] = None,
    day: Optional[str] = None,
) -> Optional[Assignment]:
    """Pick an arm for this draft on this platform, or None to leave it alone.

    `hook_arms` on the card maps an arm to the hook letter that carries it. The
    scorer then has to agree that the hook really is that arm; the card's own
    variable is what validates its own assignment, so a unit whose hooks drift
    out of shape drops out of the experiment instead of poisoning it.
    """
    h = hypothesis if hypothesis is not None else active()
    if h is None or h.status != "testing":
        return None
    if h.prediction.platform and h.prediction.platform != platform:
        return None

    hook_arms: dict = getattr(h, "hook_arms", {}) or {}
    if not hook_arms:
        return None

    # Every arm has to be producible from this draft before any of them is used.
    # Checking only the arm the coin landed on would quietly bias the design: a
    # unit whose Hook A is not investor-framed would be rejected on "investor"
    # and accepted on "scene", so it would contribute to one arm only, and the
    # difference between arms would partly be a difference between units.
    available = draft.available_hooks()
    if not eligible(draft, h, available):
        return None

    arms = sorted(hook_arms)
    day = day or date.today().isoformat()
    arm = arms[_coin(getattr(draft, "id", "") or "", h.id, day) % len(arms)]
    return Assignment(experiment=h.id, arm=arm, hook_key=hook_arms[arm])


def eligible(draft, h: cards.Hypothesis, available: Optional[dict] = None) -> bool:
    """True when this draft can carry every arm of the experiment."""
    available = draft.available_hooks() if available is None else available
    for arm, hook_key in (getattr(h, "hook_arms", {}) or {}).items():
        text = available.get(hook_key)
        if not text or h.score({"text": text}) != arm_value(h, arm):
            return False
    return True


def arm_value(h: cards.Hypothesis, arm: str) -> Optional[str]:
    """The scorer output the card expects for this arm. `hook_arms` names arms
    in the card's own vocabulary ("investor"/"scene"); the scorer speaks
    yes/no. `arm_values` bridges the two."""
    mapping = getattr(h, "arm_values", {}) or {}
    return mapping.get(arm, arm)


__all__ = ["Assignment", "active", "assign", "arm_value", "scorers"]
