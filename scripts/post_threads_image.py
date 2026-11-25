#!/usr/bin/env python3
"""Publish one already-approved Threads post that carries an image.

Loop 1 is the wrong door for this. It reads a Notion draft, may prepend a hook,
may append a CTA, and ThreadsService used to send every container as
media_type=TEXT. This script does none of that. It reads a fixed text file and
a fixed PNG, checks the text is still the approved 227 characters, and asks
ThreadsService to create an IMAGE container. Nothing is written to Notion.

The image has to be on a public HTTPS URL. graph.threads.net downloads it
itself. The workflow sets IG_CARD_URL_BASE the same way instagram.yml does
(raw.githubusercontent.com + the repo + the ref) and this script appends
assets/threads/nvda-5d-yahoo-candle.png.

    python scripts/post_threads_image.py --dry-run
    python scripts/post_threads_image.py

The access token is read from the environment inside ThreadsService. This
script never prints it. A live run also GETs the image URL with no credential
attached and stops if that GET is not a public PNG or JPEG.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import settings  # noqa: E402
from services.threads import ThreadsService, redact_secret  # noqa: E402
from utils.logging_setup import setup_logging  # noqa: E402

IMAGE_REL = "assets/threads/nvda-5d-yahoo-candle.png"
TEXT_REL = "assets/threads/nvda-tariff-post.txt"
EXPECTED_LEN = 227
_PNG = b"\x89PNG\r\n\x1a\n"
_JPEG = b"\xff\xd8\xff"
_MAX_BYTES = 8 * 1024 * 1024


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_post_text(path: Path | None = None) -> str:
    """Return the approved caption. Refuse to continue if a character changed."""
    path = path or (repo_root() / TEXT_REL)
    text = path.read_text(encoding="utf-8")
    if len(text) != EXPECTED_LEN:
        raise RuntimeError(
            f"Post text length is {len(text)}, expected {EXPECTED_LEN}. "
            "Refusing to publish an altered post."
        )
    return text


def resolve_image_url(explicit: str, base: str) -> str:
    """Public URL Meta will fetch. `explicit` wins; otherwise base + IMAGE_REL."""
    explicit = (explicit or "").strip()
    if explicit:
        url = explicit
    else:
        base = (base or "").strip().rstrip("/")
        if not base:
            raise RuntimeError(
                "IG_CARD_URL_BASE is not set — no public image_url for graph.threads.net to fetch."
            )
        url = f"{base}/{IMAGE_REL}"
    lowered = url.lower()
    if not lowered.startswith("https://") or "access_token=" in lowered:
        raise RuntimeError("Threads image_url must be a public https URL.")
    return url


def assert_image_fetchable(url: str, logger: logging.Logger) -> None:
    """GET the image with no credential. Stop before create-container if Meta
    would not be able to download a PNG or JPEG from this URL."""
    import requests

    try:
        response = requests.get(url, timeout=30, allow_redirects=True)
    except Exception as exc:
        raise RuntimeError(f"Could not fetch image URL: {exc}") from exc
    body = response.content or b""
    ctype = (response.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    logger.info(
        "public image check | status=%s | type=%s | bytes=%d",
        response.status_code, ctype or "unknown", len(body),
    )
    if not str(response.url).startswith("https://"):
        raise RuntimeError("Image URL redirected off https.")
    if response.status_code != 200:
        raise RuntimeError(f"Image URL returned HTTP {response.status_code}.")
    if not (body.startswith(_PNG) or body.startswith(_JPEG)):
        raise RuntimeError(
            f"Image URL did not return a PNG or JPEG (content-type={ctype or 'unknown'})."
        )
    if len(body) > _MAX_BYTES:
        raise RuntimeError("Image exceeds the Threads 8 MB limit.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Publish one approved Threads image post")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check the text and print the image URL. Do not call the Threads API.",
    )
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    dry_run = bool(args.dry_run)
    logger, log_path = setup_logging("threads-image", dry_run)
    token = settings.THREADS_ACCESS_TOKEN
    try:
        text = load_post_text()
        url = resolve_image_url(os.getenv("THREADS_IMAGE_URL", ""), settings.IG_CARD_URL_BASE)
        image_path = repo_root() / IMAGE_REL
        if not image_path.is_file():
            raise RuntimeError(f"Missing committed image {IMAGE_REL}")
        logger.info(
            "approved Threads image post | chars=%d | file=%s | log=%s",
            len(text), IMAGE_REL, log_path.name,
        )
        logger.info("image_url=%s", url)
        if not dry_run:
            if not token:
                raise RuntimeError("THREADS_ACCESS_TOKEN is not set.")
            if settings.THREADS_USER_ID:
                logger.info("THREADS_USER_ID is set; /me will not be called for the user id.")
            else:
                logger.info("THREADS_USER_ID is empty; the user id will be resolved from /me.")
            assert_image_fetchable(url, logger)
        media_id = ThreadsService(dry_run=dry_run, logger=logger).post_post(text, image_url=url)
        logger.info("threads media id=%s", media_id)
        return 0
    except Exception as exc:
        logger.error("Threads image post failed: %s", redact_secret(str(exc), token))
        return 1


if __name__ == "__main__":
    sys.exit(main())
