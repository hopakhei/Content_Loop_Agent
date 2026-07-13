"""Instagram — post one Quote Card as an image card.

A dedicated low-cadence flow (not part of the 5×/day text loop): pick the next
un-posted Quote Card, render it to a branded PNG (services.imagecard), and
publish it via the Instagram API. Kept separate because IG is image-only and
needs the PNG hosted at a public URL — the instagram.yml workflow renders,
commits the card so raw.githubusercontent serves it, then publishes.

`dry_run` renders the card and logs the preview but never posts. P2 of
docs/instagram-plan.md.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from config import settings
from config.schema import HOOK_FIELDS
from core.composition import select_hook
from core.tagging import COMPOSITION_VERSION, build_tags
from core.timeutil import now as hkt_now
from services.imagecard import card_quote, render_card
from services.instagram import InstagramService
from services.notion import NotionService

_ISSUE_RE = re.compile(r"^#(\d+)-(\d+)")


def run(
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None,
    notion: Optional[NotionService] = None,
    ig: Optional[InstagramService] = None,
    cards_dir: str = "cards",
) -> dict:
    log = logger or logging.getLogger("loop.instagram")
    notion = notion or NotionService(log)
    if ig is None:
        if not settings.IG_ACCESS_TOKEN and not dry_run:
            log.info("IG_ACCESS_TOKEN not set — skipping Instagram.")
            return {"posted": None, "skipped": "no-token"}
        ig = InstagramService(dry_run=dry_run, logger=log)

    posted = notion.instagram_posted_draft_ids()
    candidates = [d for d in notion.quote_card_drafts() if d.id not in posted]
    candidates.sort(key=lambda d: (d.argument_num or 0, d.title))
    if not candidates:
        log.info("No un-posted Quote Card available for Instagram.")
        return {"posted": None, "skipped": "no-candidate"}

    draft = candidates[0]
    rules = None
    try:
        rules = notion.get_rules()
    except Exception:  # rules are optional
        rules = None

    quote = card_quote(draft.post_body)
    hook_key, hook_text = select_hook(draft, rules)
    caption = _build_caption(hook_text, quote)
    out_path = f"{cards_dir.rstrip('/')}/{_slug(draft)}.png"
    render_card(quote, _issue_of(draft), out_path)

    log.info("─" * 56)
    log.info("PREVIEW IG | %s | hook=%s | card=%s", draft.title, hook_key or "none", out_path)
    for line in caption.splitlines():
        log.info("  | %s", line)
    log.info("─" * 56)

    if dry_run:
        log.info("[dry-run] card rendered; not published.")
        return {"posted": None, "card": out_path, "draft": draft.title, "caption": caption, "dry_run": True}

    if not settings.IG_CARD_URL_BASE:
        log.error("IG_CARD_URL_BASE not set — no public image_url to give Instagram.")
        return {"posted": None, "skipped": "no-url-base", "card": out_path}

    image_url = settings.IG_CARD_URL_BASE.rstrip("/") + "/" + out_path
    media_id = ig.publish_image(image_url, caption)
    notion.create_performance_record(
        draft_id=draft.id,
        post_id=media_id,
        platform="Instagram",
        posted_at=hkt_now(settings.TZ_NAME),
        hook_label=HOOK_FIELDS[hook_key][1] if hook_key else None,
        loop_version=COMPOSITION_VERSION,
        tags=build_tags(platform="Instagram", hook=hook_key, posts=[quote],
                        cta_url=None, cta_present=False, title=draft.title),
    )
    log.info("POSTED ✓ IG | '%s' | media_id=%s", draft.title, media_id)
    return {"posted": media_id, "card": out_path, "draft": draft.title, "image_url": image_url}


def _build_caption(hook_text: Optional[str], quote: str) -> str:
    parts = []
    if hook_text and hook_text.strip():
        parts.append(hook_text.strip())
    parts.append(quote)
    if settings.IG_CTA_LINE:
        parts.append(settings.IG_CTA_LINE)
    if settings.IG_HASHTAGS:
        parts.append(settings.IG_HASHTAGS)
    return "\n\n".join(parts)


def _slug(draft) -> str:
    m = _ISSUE_RE.match(draft.title or "")
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return re.sub(r"[^0-9A-Za-z]+", "-", (draft.id or "card"))[:40]


def _issue_of(draft) -> str:
    m = _ISSUE_RE.match(draft.title or "")
    return m.group(1) if m else "90s.pm"
