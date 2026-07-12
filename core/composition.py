"""Turn a Draft into the exact text that gets posted.

Composition model (see README for the rationale):

* `Post Body` is the canonical content. For non-Thread types it is a single
  post; for `Thread` it is several tweets separated by a line of `---`.
* Hook A/B/C are *alternative opening lines*. Loop 1 picks one (weighted by
  the Agent Rules, else random) and prepends it to the first post/tweet. If no
  hook fields have text, the body is posted as-is (it already leads with a hook).
* CTA: the effective URL is the draft override, else the article's CTA URL.
  If the body contains a CTA placeholder (`{CTA_URL}` or the human `[連結]`) it is
  substituted; otherwise, if no CTA is present, the standard line is appended (a new final tweet for
  threads, an appended line for single posts).
"""
from __future__ import annotations

import random
import re
from typing import Optional

from core.models import Draft, Rules

# The CTA is just the bare link — no "完整框架＋案例在 Substack 👉" sell copy,
# no "click here" gesture. `👉` is still recognised so the salesy CTA line that
# Loop 3 baked into older draft bodies gets softened to a plain link at compose
# time (no need to rewrite every draft in Notion).
CTA_TEMPLATE = "{url}"
CTA_MARKER = "👉"
# Tokens a draft may use where the CTA URL should be substituted. Drafts in the
# wild use the human placeholder [連結]; Loop 3 emits {CTA_URL}. Both are filled.
CTA_PLACEHOLDERS = (
    "{CTA_URL}", "{cta_url}",
    "[連結]", "[链接]", "[連接]", "[CTA]", "[link]", "[Link]", "[LINK]",
)
MAX_TWEET_LEN = 280
THREAD_CONTENT_TYPE = "Thread"

# Probability mass given to the winning hook when the rules name one.
WINNING_HOOK_WEIGHT = 0.7

# A thread tweet boundary is a line that is ONLY a rule of 3+ dashes / em-dashes /
# en-dashes / underscores (`---`, `———`, `___`). Anchored to the whole line, so an
# inline dash inside a sentence (e.g. "差不了多少——但…") never matches.
_THREAD_SEPARATOR_RE = re.compile(r"^[ \t]*[-–—_]{3,}[ \t]*$", re.MULTILINE)


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
    """Split a Thread body into tweets on explicit separator lines only.

    A tweet boundary is a line of 3+ dashes/em-dashes/underscores (`---` or `———`).
    Blank lines within a tweet are preserved — we never split on them, as that
    over-fragments a thread. A body with no separator line is a single tweet.
    """
    parts = [p.strip() for p in _THREAD_SEPARATOR_RE.split(body) if p.strip()]
    return parts or [body.strip()]


def _has_cta(text: str, cta_url: Optional[str]) -> bool:
    if CTA_MARKER in text:
        return True
    return bool(cta_url) and cta_url in text


def _bare_cta(segment: str, cta_url: str) -> str:
    """Collapse a sell-copy CTA line (has both 👉 and the URL) to the bare link."""
    lines = [
        cta_url if (CTA_MARKER in ln and cta_url in ln) else ln
        for ln in segment.splitlines()
    ]
    return "\n".join(lines)


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
    present = [ph for ph in CTA_PLACEHOLDERS if ph in joined]
    if cta_url and present:
        for ph in present:
            segments = [s.replace(ph, cta_url) for s in segments]
    elif cta_url and not _has_cta(joined, cta_url):
        cta_line = CTA_TEMPLATE.format(url=cta_url)
        if is_thread:
            segments.append(cta_line)
        else:
            segments[-1] = (segments[-1] + "\n\n" + cta_line).strip()

    # 1b. Soften any baked-in sell-copy CTA line ("完整框架…👉 url") down to the
    # bare link. Only a line carrying BOTH the 👉 marker and the URL is touched,
    # so an inline link inside a sentence is left alone.
    if cta_url:
        segments = [_bare_cta(s, cta_url) for s in segments]

    # 2. Prepend the chosen hook to the first post/tweet — unless the body
    # already opens with that exact hook (some drafts lead with Hook A's text;
    # prepending it again would post the same sentence twice).
    if hook_text and hook_text.strip():
        head = hook_text.strip()
        first = segments[0].strip()
        if first.startswith(head):
            segments[0] = first
        else:
            segments[0] = f"{head}\n\n{first}" if first else head

    return [s.strip() for s in segments if s.strip()]


def strip_cta(posts: list[str], cta_url: Optional[str] = None) -> list[str]:
    """Return `posts` with the CTA removed entirely — for platforms we post
    link-free. Drops any line carrying the CTA marker (`👉`) or the CTA URL,
    and drops a post that becomes empty (e.g. a thread's dedicated CTA tweet).

    Used for X while the follower count is low: the funnel matters less than
    raw reach, so we skip the link (X's ranker suppresses main posts with
    external links) and halve the write-quota cost (one tweet, not two). Never
    returns an empty list.
    """
    out: list[str] = []
    for p in posts:
        kept = [
            ln for ln in p.splitlines()
            if CTA_MARKER not in ln and not (cta_url and cta_url in ln)
        ]
        text = "\n".join(kept).strip()
        if text:
            out.append(text)
    return out or list(posts)


def length_warnings(posts: list[str], limit: int = MAX_TWEET_LEN) -> list[str]:
    """Human-readable warnings for any post exceeding the character limit."""
    warnings = []
    for i, p in enumerate(posts, start=1):
        if len(p) > limit:
            warnings.append(f"post {i}/{len(posts)} is {len(p)} chars (limit {limit})")
    return warnings
