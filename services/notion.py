"""Notion read/write wrapper.

Wraps the official `notion-client` SDK and translates between Notion's property
payloads and the plain `core.models` dataclasses. Every property name lives in
config/schema.py so a Notion rename is a one-line change here-adjacent.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any, Iterable, Optional

from config import settings
from config.schema import Articles, Drafts, Performance, PostingRules
from core.models import Article, Draft
from core.models import PostingRules as PostingRulesModel
from core.timeutil import now as hkt_now

try:
    from notion_client import Client
except ImportError:  # pragma: no cover - surfaced at runtime with a clear message
    Client = None


# ── Property extractors ──────────────────────────────────────────────────────
def _plain_text(prop: Optional[dict]) -> str:
    if not prop:
        return ""
    rich = prop.get("rich_text") or prop.get("title") or []
    return "".join(part.get("plain_text", "") for part in rich)


def _select(prop: Optional[dict]) -> Optional[str]:
    if not prop:
        return None
    sel = prop.get("select")
    return sel.get("name") if sel else None


def _multi_select(prop: Optional[dict]) -> list[str]:
    if not prop:
        return []
    return [o.get("name") for o in prop.get("multi_select", []) if o.get("name")]


def _number(prop: Optional[dict]) -> Optional[float]:
    return prop.get("number") if prop else None


def _url(prop: Optional[dict]) -> Optional[str]:
    return (prop.get("url") if prop else None) or None


def _relation_ids(prop: Optional[dict]) -> list[str]:
    if not prop:
        return []
    return [r.get("id") for r in prop.get("relation", []) if r.get("id")]


def _date(prop: Optional[dict]) -> Optional[dict]:
    if not prop:
        return None
    d = prop.get("date")
    if not d or not d.get("start"):
        return None
    return {"start": d["start"], "is_datetime": "T" in d["start"]}


class NotionService:
    def __init__(self, logger: Optional[logging.Logger] = None, client: Any = None):
        self.log = logger or logging.getLogger("loop.notion")
        if client is not None:
            self.client = client
        else:
            if Client is None:
                raise RuntimeError("notion-client is not installed. `pip install -r requirements.txt`")
            if not settings.NOTION_TOKEN:
                raise RuntimeError("NOTION_TOKEN is not set.")
            self.client = Client(auth=settings.NOTION_TOKEN)
        self._article_cache: dict[str, Article] = {}

    # ── low-level paginated query ────────────────────────────────────────────
    def _query_all(self, database_id: str, **kwargs) -> list[dict]:
        results: list[dict] = []
        cursor = None
        while True:
            payload = dict(kwargs)
            if cursor:
                payload["start_cursor"] = cursor
            resp = self.client.databases.query(database_id=database_id, **payload)
            results.extend(resp.get("results", []))
            if not resp.get("has_more"):
                break
            cursor = resp.get("next_cursor")
        return results

    # ── builders ─────────────────────────────────────────────────────────────
    @staticmethod
    def _build_draft(page: dict) -> Draft:
        p = page.get("properties", {})
        return Draft(
            id=page["id"],
            title=_plain_text(p.get(Drafts.TITLE)),
            post_body=_plain_text(p.get(Drafts.POST_BODY)),
            hooks={
                "A": _plain_text(p.get(Drafts.HOOK_A)),
                "B": _plain_text(p.get(Drafts.HOOK_B)),
                "C": _plain_text(p.get(Drafts.HOOK_C)),
            },
            content_type=_select(p.get(Drafts.CONTENT_TYPE)),
            platforms=_multi_select(p.get(Drafts.PLATFORM)),
            status=_select(p.get(Drafts.STATUS)),
            article_id=(_relation_ids(p.get(Drafts.ARTICLE)) or [None])[0],
            cta_url=_url(p.get(Drafts.CTA_URL)),
            argument_num=_number(p.get(Drafts.ARGUMENT_NUM)),
            generation=_number(p.get(Drafts.GENERATION)),
            scheduled_date=_date(p.get(Drafts.SCHEDULED_DATE)),
            source_article=_select(p.get(Drafts.SOURCE_ARTICLE)),
        )

    @staticmethod
    def _build_article(page: dict) -> Article:
        p = page.get("properties", {})
        return Article(
            id=page["id"],
            title=_plain_text(p.get(Articles.TITLE)),
            issue=_number(p.get(Articles.ISSUE_NUM)),
            cta_url=_url(p.get(Articles.CTA_URL)),
            target_per_day=_number(p.get(Articles.TARGET_PER_DAY)),
            status=_select(p.get(Articles.STATUS)),
            substack_url=_url(p.get(Articles.SUBSTACK_URL)),
            topic_summary=_plain_text(p.get(Articles.TOPIC_SUMMARY)),
            total_drafts=_number(p.get(Articles.TOTAL_DRAFTS)),
            drafts_posted=_number(p.get(Articles.DRAFTS_POSTED)),
        )

    # ── reads ────────────────────────────────────────────────────────────────
    def query_drafts_by_status(self, status: str) -> list[Draft]:
        pages = self._query_all(
            settings.NOTION_CONTENT_DRAFTS_DB,
            filter={"property": Drafts.STATUS, "select": {"equals": status}},
        )
        return [self._build_draft(pg) for pg in pages]

    def get_article(self, article_id: Optional[str]) -> Optional[Article]:
        if not article_id:
            return None
        if article_id in self._article_cache:
            return self._article_cache[article_id]
        page = self.client.pages.retrieve(page_id=article_id)
        article = self._build_article(page)
        self._article_cache[article_id] = article
        return article

    def list_articles(self) -> list[Article]:
        pages = self._query_all(settings.NOTION_ARTICLE_LIBRARY_DB)
        articles = [self._build_article(pg) for pg in pages]
        for a in articles:
            self._article_cache[a.id] = a
        return articles

    def get_posting_rules(self) -> Optional[PostingRulesModel]:
        """Read the single active Posting Rules row. Returns None if the DB is
        not configured or empty (Loop 1 then falls back to defaults)."""
        if not settings.NOTION_POSTING_RULES_DB:
            return None
        try:
            pages = self._query_all(settings.NOTION_POSTING_RULES_DB, page_size=1)
        except Exception as exc:  # pragma: no cover - network/permission issues
            self.log.warning("Could not read Posting Rules (%s); using defaults.", exc)
            return None
        if not pages:
            return None
        p = pages[0].get("properties", {})

        def _json_list(name: str) -> list:
            raw = _plain_text(p.get(name))
            if not raw:
                return []
            try:
                val = json.loads(raw)
                return val if isinstance(val, list) else [val]
            except json.JSONDecodeError:
                return [s.strip() for s in raw.split(",") if s.strip()]

        limit = _number(p.get(PostingRules.DAILY_LIMIT))
        return PostingRulesModel(
            best_slots=_json_list(PostingRules.BEST_SLOTS),
            best_content_types=_json_list(PostingRules.BEST_CONTENT_TYPES),
            best_hook_type=_select(p.get(PostingRules.BEST_HOOK_TYPE)),
            daily_limit=int(limit) if limit is not None else None,
            notes=_plain_text(p.get(PostingRules.NOTES)),
        )

    def count_posts_today(self, ref: Optional[datetime] = None) -> tuple[int, dict[str, int]]:
        """(total posts today, {article_id: count}). 'Today' is HKT calendar day.

        Counted from Post Performance `Posted At`, mapping each row back to its
        draft's article via the cached/relation lookup.
        """
        ref = ref or hkt_now(settings.TZ_NAME)
        start_of_day = ref.replace(hour=0, minute=0, second=0, microsecond=0)
        pages = self._query_all(
            settings.NOTION_PERFORMANCE_LOG_DB,
            filter={"property": Performance.POSTED_AT, "date": {"on_or_after": start_of_day.isoformat()}},
        )
        per_article: dict[str, int] = {}
        for pg in pages:
            props = pg.get("properties", {})
            draft_ids = _relation_ids(props.get(Performance.DRAFT))
            if not draft_ids:
                continue
            draft = self._build_draft(self.client.pages.retrieve(page_id=draft_ids[0]))
            if draft.article_id:
                per_article[draft.article_id] = per_article.get(draft.article_id, 0) + 1
        return len(pages), per_article

    def query_posted_needing_metrics(self, older_than_hours: int = 24) -> list[dict]:
        """Loop 2: Post Performance rows posted more than N hours ago.
        Returns raw pages (Loop 2 reads Post ID + existing metrics)."""
        cutoff = (hkt_now(settings.TZ_NAME) - timedelta(hours=older_than_hours)).isoformat()
        return self._query_all(
            settings.NOTION_PERFORMANCE_LOG_DB,
            filter={"property": Performance.POSTED_AT, "date": {"on_or_before": cutoff}},
        )

    # ── writes ───────────────────────────────────────────────────────────────
    def mark_draft_posted(self, draft_id: str) -> None:
        self.client.pages.update(
            page_id=draft_id,
            properties={Drafts.STATUS: {"select": {"name": Drafts.STATUS_POSTED}}},
        )

    def create_performance_record(
        self,
        draft_id: str,
        post_id: str,
        platform: str,
        posted_at: datetime,
        hook_label: Optional[str] = None,
        loop_version: int = 1,
    ) -> str:
        """Create the (initially blank-metrics) Post Performance row."""
        props: dict[str, Any] = {
            Performance.POST_ID: {"title": [{"text": {"content": post_id}}]},
            Performance.DRAFT: {"relation": [{"id": draft_id}]},
            Performance.POSTED_AT: {"date": {"start": posted_at.isoformat()}},
            Performance.PLATFORM: {"select": {"name": platform}},
            Performance.LOOP_VERSION: {"number": loop_version},
        }
        if hook_label:
            props[Performance.HOOK_USED] = {"select": {"name": hook_label}}
        page = self.client.pages.create(
            parent={"database_id": settings.NOTION_PERFORMANCE_LOG_DB},
            properties=props,
        )
        return page["id"]

    def update_performance_metrics(self, page_id: str, metrics: dict[str, float]) -> None:
        """Loop 2: write engagement numbers onto an existing Post Performance row.
        `metrics` keys are config.schema.Performance property names (numbers only)."""
        props = {name: {"number": value} for name, value in metrics.items() if value is not None}
        if props:
            self.client.pages.update(page_id=page_id, properties=props)

    def get_performance_rows(self, since_days: int = 30) -> list[dict]:
        """Loop 2: parsed Post Performance rows from the last `since_days`, each
        enriched with the linked draft's Content Type (for per-type analysis)."""
        cutoff = (hkt_now(settings.TZ_NAME) - timedelta(days=since_days)).isoformat()
        pages = self._query_all(
            settings.NOTION_PERFORMANCE_LOG_DB,
            filter={"property": Performance.POSTED_AT, "date": {"on_or_after": cutoff}},
        )
        rows: list[dict] = []
        draft_type_cache: dict[str, Optional[str]] = {}
        for pg in pages:
            p = pg.get("properties", {})
            draft_ids = _relation_ids(p.get(Performance.DRAFT))
            content_type = None
            if draft_ids:
                did = draft_ids[0]
                if did not in draft_type_cache:
                    draft = self._build_draft(self.client.pages.retrieve(page_id=did))
                    draft_type_cache[did] = draft.content_type
                content_type = draft_type_cache[did]
            date = _date(p.get(Performance.POSTED_AT))
            rows.append({
                "page_id": pg["id"],
                "post_id": _plain_text(p.get(Performance.POST_ID)),
                "draft_id": draft_ids[0] if draft_ids else None,
                "posted_at": date["start"] if date else None,
                "platform": _select(p.get(Performance.PLATFORM)),
                "hook_used": _select(p.get(Performance.HOOK_USED)),
                "content_type": content_type,
                "impressions": _number(p.get(Performance.IMPRESSIONS)) or 0.0,
                "likes": _number(p.get(Performance.LIKES)) or 0.0,
                "replies": _number(p.get(Performance.REPLIES)) or 0.0,
                "reposts": _number(p.get(Performance.REPOSTS)) or 0.0,
                "link_clicks": _number(p.get(Performance.LINK_CLICKS)) or 0.0,
            })
        return rows

    def upsert_posting_rules(self, rule_name: str, fields: dict[str, Any]) -> Optional[str]:
        """Loop 2: write the active Posting Rules row. No-op (returns None) if
        NOTION_POSTING_RULES_DB is not configured. `fields` keys are
        config.schema.PostingRules property names with pre-built Notion values."""
        if not settings.NOTION_POSTING_RULES_DB:
            self.log.warning("NOTION_POSTING_RULES_DB not set; skipping rules write.")
            return None
        existing = self._query_all(settings.NOTION_POSTING_RULES_DB, page_size=1)
        props = {PostingRules.RULE_NAME: {"title": [{"text": {"content": rule_name}}]}, **fields}
        if existing:
            page_id = existing[0]["id"]
            self.client.pages.update(page_id=page_id, properties=props)
            return page_id
        page = self.client.pages.create(
            parent={"database_id": settings.NOTION_POSTING_RULES_DB},
            properties=props,
        )
        return page["id"]

    def create_draft(
        self,
        *,
        title: str,
        post_body: str,
        hooks: dict[str, str],
        content_type: str,
        platforms: Iterable[str],
        article_id: Optional[str] = None,
        cta_url: Optional[str] = None,
        argument_num: Optional[float] = None,
        generation: int = 1,
        source_article: Optional[str] = None,
    ) -> str:
        """Loop 3: insert a generated draft (Status = Draft)."""
        props: dict[str, Any] = {
            Drafts.TITLE: {"title": [{"text": {"content": title}}]},
            Drafts.POST_BODY: {"rich_text": [{"text": {"content": post_body}}]},
            Drafts.CONTENT_TYPE: {"select": {"name": content_type}},
            Drafts.PLATFORM: {"multi_select": [{"name": p} for p in platforms]},
            Drafts.STATUS: {"select": {"name": Drafts.STATUS_DRAFT}},
            Drafts.GENERATION: {"number": generation},
        }
        for key, field_name in (("A", Drafts.HOOK_A), ("B", Drafts.HOOK_B), ("C", Drafts.HOOK_C)):
            if hooks.get(key):
                props[field_name] = {"rich_text": [{"text": {"content": hooks[key]}}]}
        if article_id:
            props[Drafts.ARTICLE] = {"relation": [{"id": article_id}]}
        if cta_url:
            props[Drafts.CTA_URL] = {"url": cta_url}
        if argument_num is not None:
            props[Drafts.ARGUMENT_NUM] = {"number": argument_num}
        if source_article:
            props[Drafts.SOURCE_ARTICLE] = {"select": {"name": source_article}}

        page = self.client.pages.create(
            parent={"database_id": settings.NOTION_CONTENT_DRAFTS_DB},
            properties=props,
        )
        return page["id"]
