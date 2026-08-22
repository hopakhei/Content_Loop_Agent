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
from difflib import SequenceMatcher
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
    winner_override: Optional[str] = None,
) -> tuple[Optional[str], Optional[str]]:
    """Pick a hook variant. Returns (key, text) e.g. ("B", "...") or (None, None).

    Honours the A/B/C experiment design: bias toward the winning hook but keep
    exploring the others. `winner_override` (a per-platform winner) takes
    precedence over the pooled `rules.best_hook_type`.
    """
    rng = rng or random
    available = draft.available_hooks()
    if not available:
        return None, None

    keys = sorted(available)
    winner = winner_override or (rules.best_hook_type if rules and rules.best_hook_type else None)
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
    """Collapse a sell-copy CTA line (👉 plus a link) to the bare effective CTA.

    Keyed on the 👉 marker + any http link, not the exact URL, so a baked-in
    Substack sell line also swaps to a platform-specific CTA (e.g. the GitHub
    repo on X) when compose is given a different destination."""
    lines = [
        cta_url if (CTA_MARKER in ln and ("http" in ln or cta_url in ln)) else ln
        for ln in segment.splitlines()
    ]
    return "\n".join(lines)


# Two ways a body opening can be the hook again, because they fail differently.
#
# _ECHO_RATIO catches "these two say the same thing": the accumulated opening
# and the hook are near-identical overall. It is what handles a hook that spans
# two of the body's sentences.
#
# _ECHO_COVERAGE catches "this sentence is already inside the hook": the hook
# says more afterwards, so the overall similarity is capped and never reaches
# _ECHO_RATIO, but the reader still gets the sentence twice. Only runs of
# _ECHO_MIN_RUN characters or longer count toward it — in Chinese, scattered
# single-character hits on 的/你/是 are noise, not repetition.
#
# _ECHO_MIN_SENTENCE is the floor that stops the coverage rule firing on a
# short sentence. 「它靠什麼賺錢？」 is six characters, five of which appear in a
# Hook A that is otherwise about something else — enough to score 0.83 and eat
# the reader-life scene 鐵律零點六 requires. A sentence has to be long enough
# for the overlap to mean something.
_ECHO_RATIO = 0.75
_ECHO_COVERAGE = 0.8
_ECHO_MIN_RUN = 4
_ECHO_MIN_SENTENCE = 12
_ECHO_OVERSHOOT = 1.15
# Only the opening of a segment can echo a hook. Past three sentences the body
# has moved on, and a stray match would eat real content.
_ECHO_MAX_SENTENCES = 3
_SENTENCE_END = re.compile(r"(?<=[。！？])")
_PUNCT = re.compile(r"[，。、；：！？「」『』（）\s,.;:!?\"'()]+")


def _norm(text: str) -> str:
    """Punctuation-free form for comparison.

    The old guard compared raw strings with `startswith`, so a hook and a body
    opening that differed by a single comma — 「月底結帳時，未必」 against
    「月底結帳時未必」 — read as different text and the post went out with its
    first sentence printed twice. Comparing on letters only is what makes the
    check survive the copy-editing that always happens to one copy and not the
    other."""
    return _PUNCT.sub("", text)


def _covered_by(sentence: str, head: str) -> float:
    """Fraction of `sentence` that already appears verbatim inside `head`,
    counting only runs of `_ECHO_MIN_RUN` characters or more."""
    if not sentence:
        return 0.0
    matched = sum(
        b.size for b in SequenceMatcher(None, sentence, head).get_matching_blocks()
        if b.size >= _ECHO_MIN_RUN
    )
    return matched / len(sentence)


def _merge_hook(segment: str, hook: str) -> str:
    """Return the first post's text: `hook` above `segment`, minus the repeat.

    Three shapes, because a body opening can relate to its hook three ways:

    1. The body already opens with the hook. Post the body alone — it is the
       hook plus whatever it goes on to say.
    2. The body's first sentence contains the hook and adds to it
       (「…但你講不出它替你做過什麼；也有幾筆你嫌貴，卻怎樣都捨不得停。」). Post the
       body alone for the same reason; prepending would print the shared half
       twice, and dropping the sentence would lose the half only it has.
    3. The body restates the hook and then moves on. Drop the restatement —
       one, two or three sentences, since Hook B is often the body's first two
       — and put the hook on top.

    A hook that opens somewhere else entirely matches none of these and leaves
    the body untouched, which is what keeps arm A and arm C's everyday scene.
    """
    head = _norm(hook)
    if not head or not segment.strip():
        return f"{hook}\n\n{segment}".strip() if segment.strip() else hook

    sentences = [s for s in _SENTENCE_END.split(segment) if s.strip()]
    if _norm(segment).startswith(head):
        return segment
    if sentences and _covered_by(head, _norm(sentences[0])) >= _ECHO_COVERAGE:
        return segment

    drop, acc = 0, ""
    for k, sentence in enumerate(sentences[:_ECHO_MAX_SENTENCES], start=1):
        one = _norm(sentence)
        acc += one
        # Once the accumulation runs past the hook, the restatement rule is
        # done: a matching prefix keeps the ratio high no matter what follows,
        # which would let it swallow the rest of the body one sentence at a
        # time. Past that point only outright containment can drop a sentence.
        restated = (len(acc) <= len(head) * _ECHO_OVERSHOOT
                    and SequenceMatcher(None, acc, head).ratio() >= _ECHO_RATIO)
        contained = (len(one) >= _ECHO_MIN_SENTENCE
                     and _covered_by(one, head) >= _ECHO_COVERAGE)
        if not (restated or contained):
            # Stop at the first sentence that is not an echo. Carrying on would
            # let a later match delete this one, which is how a body that opens
            # on the reader's own week loses the scene it needs.
            break
        drop = k

    rest = "".join(sentences[drop:]).strip() if drop else segment
    return f"{hook}\n\n{rest}" if rest else hook


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

    # 2. Prepend the chosen hook to the first post/tweet, dropping whatever the
    # body opens with if it is the same thing said again.
    if hook_text and hook_text.strip():
        segments[0] = _merge_hook(segments[0].strip(), hook_text.strip())

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
