"""Plain data models shared across loops.

Deliberately dependency-free (no notion_client / tweepy imports) so the
selection and composition logic can be unit-tested without network or SDKs.
The Notion service is responsible for building these from API payloads.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Draft:
    id: str
    title: str = ""
    post_body: str = ""
    hooks: dict[str, str] = field(default_factory=dict)  # {"A": "...", "B": "...", "C": "..."}
    content_type: Optional[str] = None
    platforms: list[str] = field(default_factory=list)   # ["X", "Threads"]
    status: Optional[str] = None
    article_id: Optional[str] = None
    cta_url: Optional[str] = None                          # draft-level override
    argument_num: Optional[float] = None
    generation: Optional[float] = None
    scheduled_date: Optional[dict] = None                 # {"start", "is_datetime"}
    source_article: Optional[str] = None

    def available_hooks(self) -> dict[str, str]:
        """Hook variants that actually have text."""
        return {k: v for k, v in self.hooks.items() if v and v.strip()}


@dataclass
class Article:
    id: str
    title: str = ""
    issue: Optional[float] = None
    cta_url: Optional[str] = None
    target_per_day: Optional[float] = None
    status: Optional[str] = None
    substack_url: Optional[str] = None
    topic_summary: str = ""
    total_drafts: Optional[float] = None
    drafts_posted: Optional[float] = None


@dataclass
class PostingRules:
    best_slots: list[str] = field(default_factory=list)
    best_content_types: list[str] = field(default_factory=list)
    best_hook_type: Optional[str] = None   # "A" / "B" / "C"
    daily_limit: Optional[int] = None
    notes: str = ""
