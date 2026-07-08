"""Loop 3 — GENERATE.

讀文章 → 裂變 → 寫入草稿庫.

Triggered manually with an article's full text. Sends it through the Loop 3
starter prompt, parses the 12 units out of Claude's response, and inserts them
into Content Drafts (Status = Draft, Generation = 1) related to the Article.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from core.parsing import map_content_type, map_platforms, map_source_article, parse_units
from services.claude import ClaudeService
from services.notion import NotionService

ARTICLE_SUFFIXES = {".md", ".txt"}


def run(
    issue_number,
    article_text: Optional[str] = None,
    cta_url: Optional[str] = None,
    article_id: Optional[str] = None,
    dry_run: bool = False,
    fresh: bool = False,
    logger: Optional[logging.Logger] = None,
    notion: Optional[NotionService] = None,
    claude: Optional[ClaudeService] = None,
    units_text: Optional[str] = None,
) -> dict:
    """Fission an article into Content Drafts.

    Two sources, exactly one required:
    - `article_text` — the raw article; sent through the Claude API
      (ANTHROPIC_API_KEY) to generate the 12 units.
    - `units_text` — pre-generated units in the generate.txt output format
      (e.g. written by Claude Code on a subscription); parsed and inserted
      with NO Anthropic API call.
    """
    if not (article_text or units_text):
        raise ValueError("Loop 3 needs article_text or units_text.")
    log = logger or logging.getLogger("loop.generate")
    notion = notion or NotionService(log)

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

    log.info("Loop 3 GENERATE | issue=%s | article=%s | dry_run=%s | source=%s",
             issue_number, article_id, dry_run, "units-file" if units_text else "claude-api")

    if units_text:
        raw = units_text  # pre-generated (subscription) — no API call
    else:
        claude = claude or ClaudeService(logger=log)
        raw = claude.generate_units(issue_number, cta_url or "", article_text)
    units = parse_units(raw)
    log.info("Parsed %d units.", len(units))

    source_article = map_source_article(issue_number)

    if fresh:
        if dry_run:
            log.info("[dry-run] fresh: existing unposted drafts for issue %s would be parked (Optimizing).", issue_number)
        else:
            parked = notion.park_drafts(source_article=source_article, article_id=article_id)
            log.info("Fresh: parked %d existing unposted draft(s) for issue %s.", parked, issue_number)

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


def discover_articles(articles_dir: str = "articles") -> list[tuple[int, Path]]:
    """(issue_number, path) for every articles/<digits>.(md|txt), sorted by issue."""
    base = Path(articles_dir)
    found = []
    for p in sorted(base.glob("*")):
        if p.suffix.lower() in ARTICLE_SUFFIXES and p.stem.isdigit():
            found.append((int(p.stem), p))
    return sorted(found)


def run_batch(
    articles_dir: str = "articles",
    dry_run: bool = False,
    fresh: bool = False,
    logger: Optional[logging.Logger] = None,
    notion: Optional[NotionService] = None,
    claude: Optional[ClaudeService] = None,
) -> dict:
    """Fission every articles/<issue>.(md|txt) file into Notion in one pass."""
    log = logger or logging.getLogger("loop.generate")
    articles = discover_articles(articles_dir)
    if not articles:
        log.warning("No article files found in %s/ (expected e.g. 102.md).", articles_dir)
        return {"articles": 0, "results": []}

    notion = notion or NotionService(log)
    claude = claude or ClaudeService(logger=log)
    log.info("Loop 3 BATCH | %d article(s): %s", len(articles), ", ".join(str(i) for i, _ in articles))

    results = []
    for issue, path in articles:
        text = path.read_text(encoding="utf-8").strip()
        if not text:
            log.warning("Skipping issue %s: %s is empty.", issue, path)
            continue
        results.append(
            run(issue_number=issue, article_text=text, dry_run=dry_run, fresh=fresh,
                logger=log, notion=notion, claude=claude)
        )
    total = sum(r["created"] for r in results)
    log.info("Loop 3 BATCH done | %d article(s) → %d drafts", len(results), total)
    return {"articles": len(results), "created": total, "results": results}
