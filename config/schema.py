"""Notion property names and option values.

These mirror the *live* Notion databases (introspected from the workspace),
not the prose in the product spec. Keep this file in sync if the Notion
schema changes — every read/write in services/notion.py routes through here,
so a rename only needs editing in one place.
"""
from __future__ import annotations


class Drafts:
    """Content Drafts — collection://216ebf08-3c4a-44fc-9467-a30bc12030a6"""

    TITLE = "Title"                       # title
    POST_BODY = "Post Body"               # text
    HOOK_A = "Hook A 反共識"               # text
    HOOK_B = "Hook B 數據衝擊"             # text
    HOOK_C = "Hook C 懸念缺口"             # text
    CONTENT_TYPE = "Content Type"         # select
    PLATFORM = "Platform"                 # multi_select  (X / Threads)
    STATUS = "Status"                     # select
    ARTICLE = "Article"                   # relation -> Article Library
    CTA_URL = "CTA URL"                   # url (override of the article CTA)
    ARGUMENT_NUM = "Argument #"           # number
    GENERATION = "Generation"             # number
    SCHEDULED_DATE = "Scheduled Date"     # date
    SOURCE_ARTICLE = "Source Article"     # select
    PERFORMANCE = "Performance"           # relation -> Post Performance

    # Status option values
    STATUS_DRAFT = "Draft"
    STATUS_SCHEDULED = "Scheduled"
    STATUS_POSTED = "Posted"
    STATUS_OPTIMIZING = "Optimizing"

    CONTENT_TYPE_THREAD = "Thread"


class Articles:
    """Article Library — collection://2089131e-0973-4b7d-8f10-3c39cef7a63f"""

    TITLE = "Article Title"               # title
    ISSUE_NUM = "Issue #"                 # number
    CTA_URL = "CTA URL"                   # url
    TARGET_PER_DAY = "Target Posts Per Day"  # number
    STATUS = "Status"                     # select  (Draft / Published / Archived)
    SUBSTACK_URL = "Substack URL"         # url
    TOPIC_SUMMARY = "Topic Summary"       # text
    TOTAL_DRAFTS = "Total Drafts"         # number
    DRAFTS_POSTED = "Drafts Posted"       # number
    CONTENT_DRAFTS = "Content Drafts"     # relation -> Content Drafts


class Performance:
    """Post Performance — collection://21e2c21c-b4ca-4d2f-823b-426f530e6fca"""

    POST_ID = "Post ID"                   # title  (the X tweet id)
    DRAFT = "Draft"                       # relation -> Content Drafts
    POSTED_AT = "Posted At"               # date
    PLATFORM = "Platform"                 # select  (X / Threads)
    HOOK_USED = "Hook Used"               # select
    IMPRESSIONS = "Impressions"           # number
    IMPRESSIONS_24H = "Impressions 24h"   # number
    IMPRESSIONS_7D = "Impressions 7d"     # number
    LIKES = "Likes"                       # number
    REPLIES = "Replies"                   # number
    REPOSTS = "Reposts"                   # number
    LINK_CLICKS = "Link Clicks"           # number
    ENGAGEMENT_SCORE = "Engagement Score"  # formula (read-only)
    AI_NOTES = "AI Notes"                 # text
    AI_SCORE = "AI Score"                 # number
    LOOP_VERSION = "Loop Version"         # number

    # Hook Used option values
    HOOK_USED_A = "A - 反共識"
    HOOK_USED_B = "B - 數據衝擊"
    HOOK_USED_C = "C - 懸念缺口"


class PostingRules:
    """Posting Rules — written by Loop 2, read by Loop 1.

    This database does not exist in the workspace yet (no ID in the spec).
    These names are the proposed schema; create the DB with matching property
    names and set NOTION_POSTING_RULES_DB. Loop 1 degrades gracefully without it.
    """

    RULE_NAME = "Rule Name"               # title
    BEST_SLOTS = "Best Slots"             # rich_text (JSON array)
    BEST_CONTENT_TYPES = "Best Content Types"  # rich_text (JSON array)
    BEST_HOOK_TYPE = "Best Hook Type"     # select  (A / B / C)
    DAILY_LIMIT = "Daily Limit"           # number
    UPDATED_AT = "Updated At"             # date
    NOTES = "Notes"                       # rich_text


# Hook key (A/B/C) -> (Content Drafts hook field, Performance "Hook Used" option)
HOOK_FIELDS = {
    "A": (Drafts.HOOK_A, Performance.HOOK_USED_A),
    "B": (Drafts.HOOK_B, Performance.HOOK_USED_B),
    "C": (Drafts.HOOK_C, Performance.HOOK_USED_C),
}
