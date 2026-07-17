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
from core.composition import effective_cta_url, select_hook
from core.tagging import COMPOSITION_VERSION, build_tags
from core.timeutil import now as hkt_now
from services.imagecard import card_quote, load_carousel_spec, render_card, render_carousel
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

    # Resolve this card's real CTA (draft override → its Article's CTA), the same
    # per-issue link X/Threads carry, so the caption points at the right article
    # instead of a generic "link in bio".
    article = None
    if draft.article_id:
        try:
            article = notion.get_article(draft.article_id)
        except Exception:  # article lookup is best-effort; never fail the post on it
            article = None
    cta = effective_cta_url(draft, article.cta_url if article else None)

    quote = card_quote(draft.post_body)
    ig_winner = (rules.best_hook_by_platform.get("Instagram") if rules else None)
    hook_key, hook_text = select_hook(draft, rules, winner_override=ig_winner)
    caption = _build_caption(hook_text, quote, cta)
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
    if cta:
        ig.post_comment(media_id, f"全文：{cta}")
    notion.create_performance_record(
        draft_id=draft.id,
        post_id=media_id,
        platform="Instagram",
        posted_at=hkt_now(settings.TZ_NAME),
        hook_label=HOOK_FIELDS[hook_key][1] if hook_key else None,
        loop_version=COMPOSITION_VERSION,
        tags=build_tags(platform="Instagram", hook=hook_key, posts=[quote],
                        cta_url=cta, cta_present=bool(cta), title=draft.title),
    )
    log.info("POSTED ✓ IG | '%s' | media_id=%s", draft.title, media_id)
    return {"posted": media_id, "card": out_path, "draft": draft.title, "image_url": image_url}


def run_carousel(
    issue: str,
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None,
    notion: Optional[NotionService] = None,
    ig: Optional[InstagramService] = None,
    cards_dir: str = "cards",
    spec_dir: str = "carousels",
) -> dict:
    """Publish one article's reviewed slide script (carousels/<issue>.json) as
    an IG carousel. Manual per-issue dispatch — each set is human-reviewed
    before it ships, so there is no automatic rotation here."""
    log = logger or logging.getLogger("loop.instagram")
    spec = load_carousel_spec(f"{spec_dir.rstrip('/')}/{issue}.json")
    cta = (spec.get("cta_url") or "").strip()
    caption = (spec.get("caption") or "").replace("{CTA_URL}", cta).strip()

    out_dir = f"{cards_dir.rstrip('/')}/carousel-{issue}"
    paths = render_carousel(spec, out_dir)
    log.info("─" * 56)
    log.info("PREVIEW IG CAROUSEL | #%s | %d slides → %s", issue, len(paths), out_dir)
    for line in caption.splitlines():
        log.info("  | %s", line)
    log.info("─" * 56)

    if dry_run:
        log.info("[dry-run] %d slides rendered; not published.", len(paths))
        return {"posted": None, "slides": paths, "caption": caption, "dry_run": True}

    if ig is None:
        if not settings.IG_ACCESS_TOKEN:
            log.info("IG_ACCESS_TOKEN not set — skipping Instagram carousel.")
            return {"posted": None, "skipped": "no-token", "slides": paths}
        ig = InstagramService(dry_run=dry_run, logger=log)
    if not settings.IG_CARD_URL_BASE:
        log.error("IG_CARD_URL_BASE not set — no public image_url to give Instagram.")
        return {"posted": None, "skipped": "no-url-base", "slides": paths}

    base = settings.IG_CARD_URL_BASE.rstrip("/")
    image_urls = [f"{base}/{p}" for p in paths]
    media_id = ig.publish_carousel(image_urls, caption)
    if cta:
        ig.post_comment(media_id, f"全文：{cta}")

    notion = notion or NotionService(log)
    slide_texts = [s.get("head", "") for s in spec["slides"]]
    notion.create_performance_record(
        draft_id=None,
        post_id=media_id,
        platform="Instagram",
        posted_at=hkt_now(settings.TZ_NAME),
        loop_version=COMPOSITION_VERSION,
        tags=build_tags(platform="Instagram", hook=None, posts=slide_texts,
                        cta_url=cta or None, cta_present=bool(cta and cta in caption),
                        title=f"#{issue}-carousel", extra={"format": "carousel"}),
    )
    log.info("POSTED ✓ IG CAROUSEL | #%s | %d slides | media_id=%s", issue, len(paths), media_id)
    return {"posted": media_id, "slides": paths, "image_urls": image_urls}


def _build_caption(hook_text: Optional[str], quote: str, cta_url: Optional[str] = None) -> str:
    parts = []
    if hook_text and hook_text.strip():
        parts.append(hook_text.strip())
    parts.append(quote)
    # The card's real article link (bare, no sell copy) when we have one; else
    # fall back to the generic "link in bio" line. IG caption links aren't
    # clickable, but showing the correct URL beats pointing at a generic bio.
    if cta_url:
        parts.append(cta_url)
    elif settings.IG_CTA_LINE:
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
