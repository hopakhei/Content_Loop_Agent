"""Turn a Draft into the exact text that gets posted.

Composition model (see README for the rationale):

* `Post Body` is the canonical content. For non-Thread types it is a single
  post; for `Thread` it is several tweets separated by a line of `---`.
* Hook A/B/C are *alternative opening lines*. Loop 1 picks one (weighted by
  the Agent Rules, else random) and prepends it to the first post/tweet. If no
  hook fields have text, the body is posted as-is (it already leads with a hook).
* CTA: the effective URL is the draft override, else the article's CTA URL.
  If the body contains the `{CTA_URL}` placeholder it is substituted; otherwise,
  if no CTA is present, the standard CTA line is appended (a new final tweet for
  threads, an appended line for single posts).
"""
from __future__ import annotations

import random
import re
from typing import Optional

from core.models import Draft, Rules

CTA_TEMPLATE = "完整框架＋案例在 Substack 👉 {url}"
CTA_MARKER = "👉"
CTA_PLACEHOLDER = "{CTA_URL}"
MAX_TWEET_LEN = 280
THREAD_CONTENT_TYPE = "Thread"

# Probability mass given to the winning hook when the rules name one.
WINNING_HOOK_WEIGHT = 0.7

_THREAD_SEPARATOR_RE = re.compile(r"^\s*-{3,}\s*$", re.MULTILINE)
_BLANKLINE_RE = re.compile(r"\n\s*\n")


def effective_cta_url(draft: Draft, article_cta_url: Optional[str]) -> Optional[str]:
    """Draft-level CTA overrides the article CTA."""
    return (draft.cta_url or "").strip() or (article_cta_url or "").strip() or None


def select_hook(
    draft: Draft,
    rules: Optional[Rules] = None,
    rng: Optional[random.Random] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Pick a hook variant. Returns (key, text) e.g. ("B", "...") or (None, None).

    Honours the A/B/C experiment design: bias toward the winning hook from the
    rules but keep exploring the others.
    """
    rng = rng or random
    available = draft.available_hooks()
    if not available:
        return None, None

    keys = sorted(available)
    winner = rules.best_hook_type if rules and rules.best_hook_type else None
    if winner in available and len(keys) > 1:
        others = [k for k in keys if k != winner]
        weights = []
        for k in keys:
            if k == winner:
                weights.append(WINNING_HOOK_WEIGHT)
            else:
                weights.append((1 - WINNING_HOOK_WEIGHT) / len(others))
        key = rng.choices(keys, weights=weights, k=1)[0]
    else:
        key = rng.choice(keys)
    return key, available[key]


def split_thread(body: str) -> list[str]:
    """Split a Thread body into individual tweets.

    Primary convention: a line containing only `---` separates tweets.
    Fallback: split on blank lines. Always returns at least one segment.
    """
    parts = [p.strip() for p in _THREAD_SEPARATOR_RE.split(body) if p.strip()]
    if len(parts) <= 1:
        parts = [p.strip() for p in _BLANKLINE_RE.split(body) if p.strip()]
    return parts or [body.strip()]


def _has_cta(text: str, cta_url: Optional[str]) -> bool:
    if CTA_MARKER in text:
        return True
    return bool(cta_url) and cta_url in text


def compose_posts(
    draft: Draft,
    hook_text: Optional[str],
    cta_url: Optional[str],
) -> list[str]:
    """Build the ordered list of post texts (one item, or many for a thread)."""
    body = (draft.post_body or "").strip()
    is_thread = (draft.content_type or "") == THREAD_CONTENT_TYPE
    segments = split_thread(body) if is_thread else [body]
    segments = [s for s in segments if s] or [""]

    # 1. CTA substitution / injection.
    joined = "\n".join(segments)
    if CTA_PLACEHOLDER in joined:
        segments = [s.replace(CTA_PLACEHOLDER, cta_url or "") for s in segments]
    elif cta_url and not _has_cta(joined, cta_url):
        cta_line = CTA_TEMPLATE.format(url=cta_url)
        if is_thread:
            segments.append(cta_line)
        else:
            segments[-1] = (segments[-1] + "\n\n" + cta_line).strip()

    # 2. Prepend the chosen hook to the first post/tweet.
    if hook_text and hook_text.strip():
        head = hook_text.strip()
        first = segments[0].strip()
        segments[0] = f"{head}\n\n{first}" if first else head

    return [s.strip() for s in segments if s.strip()]


def length_warnings(posts: list[str], limit: int = MAX_TWEET_LEN) -> list[str]:
    """Human-readable warnings for any post exceeding the character limit."""
    warnings = []
    for i, p in enumerate(posts, start=1):
        if len(p) > limit:
            warnings.append(f"post {i}/{len(posts)} is {len(p)} chars (limit {limit})")
    return warnings
