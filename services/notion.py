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
from config.schema import AgentRules, Articles, Drafts, Performance
from core.models import Article, Draft
from core.models import Rules as RulesModel
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


def _safe_json_list(raw: str) -> list:
    """Parse a JSON array; fall back to comma-splitting a plain string."""
    if not raw:
        return []
    try:
        val = json.loads(raw)
        return val if isinstance(val, list) else [val]
    except json.JSONDecodeError:
        return [s.strip() for s in raw.split(",") if s.strip()]


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
    def _query_all(self, data_source_id: str, **kwargs) -> list[dict]:
        results: list[dict] = []
        cursor = None
        while True:
            payload = dict(kwargs)
            if cursor:
                payload["start_cursor"] = cursor
            resp = self.client.data_sources.query(data_source_id=data_source_id, **payload)
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

    def get_rules(self) -> Optional[RulesModel]:
        """Read the operational rules from the `Active` rows of Agent Rules.

        Returns the parsed operational config (daily limit, best hook, best slots,
        best content types, summary notes), or None if the DB is unset/empty or has
        no operational rows — Loop 1 then falls back to defaults.
        """
        if not settings.NOTION_AGENT_RULES_DB:
            return None
        try:
            pages = self._query_all(
                settings.NOTION_AGENT_RULES_DB,
                filter={"property": AgentRules.STATUS, "select": {"equals": AgentRules.STATUS_ACTIVE}},
            )
        except Exception as exc:  # pragma: no cover - network/permission issues
            self.log.warning("Could not read Agent Rules (%s); using defaults.", exc)
            return None
        if not pages:
            return None

        daily_limit = best_hook = None
        best_slots: list = []
        best_content_types: list = []
        notes = ""
        found = False
        for pg in pages:
            p = pg.get("properties", {})
            title = _plain_text(p.get(AgentRules.RULE_TITLE)).strip()
            content = _plain_text(p.get(AgentRules.RULE_CONTENT)).strip()
            if title == AgentRules.RULE_DAILY_LIMIT:
                found = True
                try:
                    daily_limit = int(float(content))
                except ValueError:
                    pass
            elif title == AgentRules.RULE_BEST_HOOK:
                found = True
                key = content[:1].upper()
                best_hook = key if key in {"A", "B", "C"} else None
            elif title == AgentRules.RULE_BEST_SLOTS:
                found = True
                best_slots = _safe_json_list(content)
            elif title == AgentRules.RULE_BEST_CONTENT_TYPES:
                found = True
                best_content_types = _safe_json_list(content)
            elif title == AgentRules.RULE_LEARN_SUMMARY:
                notes = content

        if not found:
            return None
        return RulesModel(
            best_slots=best_slots,
            best_content_types=best_content_types,
            best_hook_type=best_hook,
            daily_limit=daily_limit,
            notes=notes,
        )

    def verify_databases(self) -> list[tuple[str, bool, str]]:
        """Read-only preflight: confirm each configured data source is reachable
        (token valid + shared with the integration). Returns (label, ok, detail)."""
        targets = [
            ("Article Library", settings.NOTION_ARTICLE_LIBRARY_DB),
            ("Content Drafts", settings.NOTION_CONTENT_DRAFTS_DB),
            ("Post Performance", settings.NOTION_PERFORMANCE_LOG_DB),
            ("Agent Rules", settings.NOTION_AGENT_RULES_DB),
        ]
        results: list[tuple[str, bool, str]] = []
        for label, ds_id in targets:
            if not ds_id:
                results.append((label, False, "id not configured"))
                continue
            try:
                self.client.data_sources.retrieve(data_source_id=ds_id)
                results.append((label, True, "reachable"))
            except Exception as exc:  # report any failure (404 = not shared, 401 = bad token)
                results.append((label, False, str(exc)[:140]))
        return results

    def park_drafts(self, source_article: Optional[str] = None, article_id: Optional[str] = None) -> int:
        """Loop 3 fresh-start: move this article's UNPOSTED drafts (Draft/Scheduled)
        to Status=Optimizing so Loop 1 stops selecting them. Matches by Source
        Article select and/or Article relation. Returns how many were parked."""
        if not (source_article or article_id):
            return 0
        parked = 0
        for status in (Drafts.STATUS_DRAFT, Drafts.STATUS_SCHEDULED):
            for d in self.query_drafts_by_status(status):
                if (source_article and d.source_article == source_article) or (
                    article_id and d.article_id == article_id
                ):
                    self.client.pages.update(
                        page_id=d.id,
                        properties={Drafts.STATUS: {"select": {"name": Drafts.STATUS_OPTIMIZING}}},
                    )
                    parked += 1
        return parked

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
        # A draft posted to multiple platforms creates one Performance row per
        # platform but is ONE posting event — count distinct drafts.
        seen: set = set()
        total = 0
        per_article: dict[str, int] = {}
        for pg in pages:
            props = pg.get("properties", {})
            draft_ids = _relation_ids(props.get(Performance.DRAFT))
            key = draft_ids[0] if draft_ids else pg["id"]
            if key in seen:
                continue
            seen.add(key)
            total += 1
            if not draft_ids:
                continue
            draft = self._build_draft(self.client.pages.retrieve(page_id=draft_ids[0]))
            if draft.article_id:
                per_article[draft.article_id] = per_article.get(draft.article_id, 0) + 1
        return total, per_article

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
            parent={"type": "data_source_id", "data_source_id": settings.NOTION_PERFORMANCE_LOG_DB},
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

    def get_next_loop_iteration(self) -> int:
        """The next LEARN iteration number = max existing `Loop` + 1 (>=1)."""
        if not settings.NOTION_AGENT_RULES_DB:
            return 1
        try:
            pages = self._query_all(settings.NOTION_AGENT_RULES_DB)
        except Exception:  # pragma: no cover - network/permission issues
            return 1
        highest = 0
        for pg in pages:
            v = _number(pg.get("properties", {}).get(AgentRules.LOOP))
            if v:
                highest = max(highest, int(v))
        return highest + 1

    def _find_rule_page(self, title: str) -> Optional[dict]:
        pages = self._query_all(
            settings.NOTION_AGENT_RULES_DB,
            filter={"property": AgentRules.RULE_TITLE, "title": {"equals": title}},
            page_size=1,
        )
        return pages[0] if pages else None

    def _upsert_rule(
        self,
        title: str,
        category: str,
        content: str,
        confidence: Optional[int],
        evidence: str,
        loop: int,
        status: str = AgentRules.STATUS_ACTIVE,
    ) -> str:
        """Upsert a single Agent Rules row by title, bumping its Version."""
        existing = self._find_rule_page(title)
        props: dict[str, Any] = {
            AgentRules.RULE_TITLE: {"title": [{"text": {"content": title}}]},
            AgentRules.RULE_CONTENT: {"rich_text": [{"text": {"content": content}}]},
            AgentRules.CATEGORY: {"select": {"name": category}},
            AgentRules.STATUS: {"select": {"name": status}},
            AgentRules.LOOP: {"number": loop},
        }
        if confidence is not None:
            props[AgentRules.CONFIDENCE] = {"number": confidence}
        if evidence:
            props[AgentRules.EVIDENCE_POST_IDS] = {"rich_text": [{"text": {"content": evidence}}]}
        if existing:
            prev = _number(existing.get("properties", {}).get(AgentRules.VERSION)) or 0
            props[AgentRules.VERSION] = {"number": int(prev) + 1}
            self.client.pages.update(page_id=existing["id"], properties=props)
            return existing["id"]
        props[AgentRules.VERSION] = {"number": 1}
        page = self.client.pages.create(
            parent={"type": "data_source_id", "data_source_id": settings.NOTION_AGENT_RULES_DB},
            properties=props,
        )
        return page["id"]

    def write_rules(
        self,
        *,
        daily_limit: int,
        best_hook: Optional[str],
        best_slots: list,
        best_content_types: list,
        confidence: int,
        evidence_post_ids: list[str],
        loop_iteration: int,
        summary: str,
    ) -> bool:
        """Loop 2: upsert the operational rules (+ a human summary) into Agent
        Rules as `Active` rows. No-op (returns False) if the DB is not configured."""
        if not settings.NOTION_AGENT_RULES_DB:
            self.log.warning("NOTION_AGENT_RULES_DB not set; skipping rules write.")
            return False
        evidence = ",".join(evidence_post_ids[:50])

        # Daily Limit is config, not learned -> full confidence, no evidence.
        self._upsert_rule(
            AgentRules.RULE_DAILY_LIMIT, AgentRules.CAT_META, str(daily_limit),
            confidence=100, evidence="", loop=loop_iteration,
        )
        if best_hook:
            self._upsert_rule(
                AgentRules.RULE_BEST_HOOK, AgentRules.CAT_HOOK, best_hook,
                confidence, evidence, loop_iteration,
            )
        self._upsert_rule(
            AgentRules.RULE_BEST_SLOTS, AgentRules.CAT_TIMING,
            json.dumps(best_slots, ensure_ascii=False), confidence, evidence, loop_iteration,
        )
        self._upsert_rule(
            AgentRules.RULE_BEST_CONTENT_TYPES, AgentRules.CAT_STRUCTURE,
            json.dumps(best_content_types, ensure_ascii=False), confidence, evidence, loop_iteration,
        )
        self._upsert_rule(
            AgentRules.RULE_LEARN_SUMMARY, AgentRules.CAT_META, summary[:1900],
            confidence, evidence, loop_iteration,
        )
        return True

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
            parent={"type": "data_source_id", "data_source_id": settings.NOTION_CONTENT_DRAFTS_DB},
            properties=props,
        )
        return page["id"]
