"""Loop 3 — GENERATE.

讀文章 → 裂變 → 寫入草稿庫.

Triggered manually with an article's full text. Sends it through the Loop 3
starter prompt, parses the 12 units out of Claude's response, and inserts them
into Content Drafts (Status = Draft, Generation = 1) related to the Article.
"""
from __future__ import annotations

import logging
from typing import Optional

from core.parsing import map_content_type, map_platforms, map_source_article, parse_units
from services.claude import ClaudeService
from services.notion import NotionService


def run(
    issue_number,
    article_text: str,
    cta_url: Optional[str] = None,
    article_id: Optional[str] = None,
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None,
    notion: Optional[NotionService] = None,
    claude: Optional[ClaudeService] = None,
) -> dict:
    log = logger or logging.getLogger("loop.generate")
    notion = notion or NotionService(log)
    claude = claude or ClaudeService(logger=log)

    # Resolve the Article (for relation + CTA inheritance) by id or Issue #.
    article = None
    if article_id:
        article = notion.get_article(article_id)
    else:
        for a in notion.list_articles():
            if a.issue is not None and int(a.issue) == int(issue_number):
                article = a
                break
    if article:
        article_id = article.id
        cta_url = cta_url or article.cta_url
    if not cta_url:
        log.warning("No CTA URL resolved for issue %s; bodies will keep any {CTA_URL} placeholder.", issue_number)

    log.info("Loop 3 GENERATE | issue=%s | article=%s | dry_run=%s", issue_number, article_id, dry_run)

    raw = claude.generate_units(issue_number, cta_url or "", article_text)
    units = parse_units(raw)
    log.info("Claude returned %d parseable units.", len(units))

    source_article = map_source_article(issue_number)
    created: list[dict] = []
    for unit in units:
        content_type = map_content_type(unit.content_type_label)
        platforms = map_platforms(unit.platform_label)
        if not content_type:
            log.warning("Unit %s: could not map content type '%s'; skipping.", unit.number, unit.content_type_label)
            continue
        title = f"#{issue_number}-{unit.number:02d} {content_type}"
        record = {
            "title": title,
            "content_type": content_type,
            "platforms": platforms,
            "argument_num": float(unit.number),
            "hooks": unit.hooks,
        }
        if dry_run:
            log.info("[dry-run] would create draft: %s | platforms=%s", title, platforms)
            created.append(record)
            continue

        draft_id = notion.create_draft(
            title=title,
            post_body=unit.post_body,
            hooks=unit.hooks,
            content_type=content_type,
            platforms=platforms,
            article_id=article_id,
            cta_url=cta_url,
            argument_num=float(unit.number),
            generation=1,
            source_article=source_article,
        )
        record["draft_id"] = draft_id
        created.append(record)
        log.info("Created draft %s (%s)", title, draft_id)

    log.info("Loop 3 done | created=%d drafts for issue %s", len(created), issue_number)
    return {"issue": issue_number, "units": len(units), "created": len(created), "drafts": created}
