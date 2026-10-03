#!/usr/bin/env python3
"""Publish one long article to X and Threads, word for word.

The daily pipeline is the wrong door for this. Loop 1 reads drafts out of
Notion, picks a hook, composes an opening, appends a CTA and is filtered by
POST_FRAMEWORKS_ONLY — every one of those steps rewrites the text, and the
thing being published here is a finished article that must go out unchanged.
So this is a separate door: a file in `longform/`, dispatched by hand.

    python scripts/post_longform.py longform/x.md --segments-only   # inspect
    python scripts/post_longform.py longform/x.md --dry-run         # no network
    python scripts/post_longform.py longform/x.md --platforms X,Threads

The only transformation applied is where the text is cut:

  X       one post when the article fits X_LONGPOST_LIMIT (25,000 with
          Premium), which is the case for anything of article length; a 280-char
          chain otherwise.
  Threads 500 characters a post, chained as replies.

Cuts land on blank lines, then on sentence ends, then on commas, and a URL is
never split. `verify_verbatim` re-joins the segments and compares them to the
source — if a character went missing the run stops before anything is posted.
"""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402

THREADS_LIMIT = 500
X_CHAIN_LIMIT = 280
JOIN = "\n\n"

_PARA = re.compile(r"\n\s*\n")
# Keep the terminator with the sentence it ends, closing quotes included.
_SENTENCE = re.compile(r"(?<=[。！？])(?![」』）】\"'])")
_URL = re.compile(r"https?://\S+")
# A numbered section heading always opens a post. Left to the packer, a heading
# lands wherever the character count happens to run out, and the one place it
# must not land is the bottom of a post — the reader gets a title with nothing
# under it and the section it names starts in the next reply.
_HEADING = re.compile(r"^[一二三四五六七八九十]+、")
# A line of three or more dashes is the author saying "the post ends here".
# Same marker core/composition.py already uses to split a thread, so a draft
# written for one path reads the same in the other. When a file carries these,
# the automatic packer stands down entirely — the writer has done the cutting,
# and the only job left is to check that each block fits.
_EXPLICIT = re.compile(r"^[ \t]*[-–—_]{3,}[ \t]*$", re.M)


def paragraphs(text: str) -> list[str]:
    return [p.strip() for p in _PARA.split(text.strip()) if p.strip()]


def _sentences(para: str) -> list[str]:
    return [s for s in _SENTENCE.split(para) if s]


def _commas(sentence: str) -> list[str]:
    """Last resort before a blind cut. Splits after 、，；: never inside a URL,
    because a URL broken across two posts is a dead link in both."""
    out, start = [], 0
    for m in re.finditer(r"[，、；]", sentence):
        i = m.end()
        if any(u.start() < i < u.end() for u in _URL.finditer(sentence)):
            continue
        out.append(sentence[start:i])
        start = i
    if start < len(sentence):
        out.append(sentence[start:])
    return out or [sentence]


def _pack(pieces: list[str], limit: int, glue: str) -> list[str]:
    out, buf = [], ""
    for piece in pieces:
        if not buf:
            buf = piece
        elif len(buf) + len(glue) + len(piece) <= limit:
            buf += glue + piece
        else:
            out.append(buf)
            buf = piece
    if buf:
        out.append(buf)
    return out


def _fit(para: str, limit: int) -> list[str]:
    """One paragraph as one or more pieces, none longer than `limit`."""
    if len(para) <= limit:
        return [para]
    pieces = _pack(_sentences(para), limit, "")
    if all(len(p) <= limit for p in pieces):
        return pieces
    out = []
    for piece in pieces:
        if len(piece) <= limit:
            out.append(piece)
            continue
        out.extend(_pack(_commas(piece), limit, ""))
    over = [p for p in out if len(p) > limit]
    if over:
        raise ValueError(
            f"cannot cut this without breaking a word ({len(over[0])} chars, "
            f"limit {limit}): {over[0][:60]}…"
        )
    return out


def sections(text: str) -> list[list[str]]:
    """Paragraphs grouped by numbered heading. Posts never straddle a group."""
    out: list[list[str]] = []
    for para in paragraphs(text):
        if not out or _HEADING.match(para):
            out.append([])
        out[-1].append(para)
    return out


def explicit_blocks(text: str) -> list[str] | None:
    """The author's own post breaks, or None when the file has none."""
    if not _EXPLICIT.search(text):
        return None
    return [b.strip() for b in _EXPLICIT.split(text) if b.strip()]


def flatten(text: str) -> str:
    """The article without its break markers — what the reader ends up with."""
    blocks = explicit_blocks(text)
    return "\n\n".join(blocks) if blocks else text.strip()


def segment(text: str, limit: int) -> list[str]:
    """The article as posts of at most `limit` characters each.

    Paragraphs stay whole and travel together while they fit, so a post ends
    where the writing already ended rather than wherever the count ran out.
    An author's own breaks override all of that and are never second-guessed:
    a block over the limit stops the run rather than being quietly re-cut,
    because the fix is a decision about the writing, not about arithmetic.
    """
    blocks = explicit_blocks(text)
    if blocks is not None:
        over = [(i, b) for i, b in enumerate(blocks, 1) if len(b) > limit]
        if over:
            i, b = over[0]
            raise ValueError(
                f"block {i} of {len(blocks)} is {len(b)} characters, over the "
                f"{limit} limit — split it in the file: {b[:60]}…")
        return blocks

    posts: list[str] = []
    for group in sections(text):
        pieces: list[str] = []
        for para in group:
            pieces.extend(_fit(para, limit))
        posts.extend(_pack(pieces, limit, JOIN))
    return posts


def verify_verbatim(source: str, segments: list[str]) -> None:
    """Every character of the article, in order, is somewhere in the chain.

    Compared with whitespace removed: the cuts themselves add and drop line
    breaks, and those are the only edits this script is allowed to make.
    """
    want = re.sub(r"\s+", "", source)
    got = re.sub(r"\s+", "", "".join(segments))
    if want == got:
        return
    i = next((i for i, (a, b) in enumerate(zip(want, got)) if a != b), min(len(want), len(got)))
    raise ValueError(
        f"segmentation is not verbatim — diverges at character {i}: "
        f"source {want[i:i + 40]!r} vs segments {got[i:i + 40]!r}"
    )


def plan(text: str, platforms: list[str]) -> dict[str, list[str]]:
    flat = flatten(text)
    out: dict[str, list[str]] = {}
    if "X" in platforms:
        # Author breaks are Threads-shaped. On X the whole piece fits one post,
        # so the breaks become blank lines rather than twenty separate writes.
        limit = settings.X_LONGPOST_LIMIT if settings.X_LONGPOST else X_CHAIN_LIMIT
        out["X"] = [flat] if len(flat) <= limit else segment(text, X_CHAIN_LIMIT)
    if "Threads" in platforms:
        out["Threads"] = segment(text, THREADS_LIMIT)
    for posts in out.values():
        verify_verbatim(flat, posts)
    return out


def _report(log, posts_by_platform: dict[str, list[str]]) -> None:
    for platform, posts in posts_by_platform.items():
        log.info("── %s: %d post%s", platform, len(posts), "" if len(posts) == 1 else "s")
        for i, p in enumerate(posts, 1):
            head = p.splitlines()[0] if p.splitlines() else ""
            log.info("  [%2d/%d] %4d chars | %s", i, len(posts), len(p), head[:48])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help="the article file (plain text or markdown)")
    ap.add_argument("--platforms", default="X,Threads")
    ap.add_argument("--dry-run", action="store_true", help="compose, never post")
    ap.add_argument("--segments-only", action="store_true",
                    help="print the segmentation and exit without touching the network")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    log = logging.getLogger("longform")

    text = Path(args.path).read_text("utf-8").strip()
    platforms = [p.strip() for p in args.platforms.split(",") if p.strip()]
    posts_by_platform = plan(text, platforms)

    log.info("%s — %d characters%s", args.path, len(flatten(text)),
             " (author's own breaks)" if explicit_blocks(text) else "")
    _report(log, posts_by_platform)

    if args.segments_only:
        for platform, posts in posts_by_platform.items():
            print(f"\n{'=' * 60}\n{platform}\n{'=' * 60}")
            for i, p in enumerate(posts, 1):
                print(f"\n--- {i}/{len(posts)} ({len(p)} chars) ---\n{p}")
        return

    from services.errors import PartialThreadError  # noqa: E402
    from services.threads import ThreadsService     # noqa: E402
    from services.twitter import TwitterService     # noqa: E402

    failures = []
    for platform, posts in posts_by_platform.items():
        try:
            # Inside the try: missing credentials for one platform must not stop
            # the other from publishing.
            client = (TwitterService if platform == "X" else ThreadsService)(
                dry_run=args.dry_run, logger=log)
            ids = client.post_thread(posts)
        except PartialThreadError as exc:
            # The root is live. Say how far it got — the rest is added by hand,
            # never by re-running this, which would duplicate the opening post.
            log.error("PARTIAL on %s: %d/%d posts live (%s). Root id %s.",
                      platform, len(exc.ids), len(posts), exc.cause, exc.ids[0])
            failures.append(platform)
            continue
        except Exception as exc:
            log.error("FAILED on %s: %s", platform, exc)
            failures.append(platform)
            continue
        log.info("POSTED ✓ %s | %d posts | root id %s", platform, len(ids), ids[0])

    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
