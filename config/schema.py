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


class AgentRules:
    """Agent Rules — the single source of truth for learned rules.

    Loop 2 (LEARN) writes rules here; Loop 1 (POST) reads the `Active`
    *operational* rows (identified by RULE_* titles below) and parses their
    `Rule Content`. Narrative rows (insights, failures) coexist for humans and
    are simply ignored by Loop 1. Set NOTION_AGENT_RULES_DB. Loop 1 degrades
    gracefully (DAILY_HARD_LIMIT + random hooks) when the DB is unset/empty.
    """

    RULE_TITLE = "Rule Title"             # title
    RULE_CONTENT = "Rule Content"         # text  (machine value for operational rows)
    CATEGORY = "Category"                 # select
    STATUS = "Status"                     # select
    CONFIDENCE = "Confidence"             # number 0-100
    EVIDENCE_POST_IDS = "Evidence Post IDs"  # text (comma-separated Post IDs)
    LOOP = "Loop"                         # number (LEARN iteration)
    VERSION = "Version"                   # number
    DEPRECATION_REASON = "Deprecation Reason"  # text
    # Created At / Last Updated are system (created_time / last_edited_time).

    # Category options
    CAT_HOOK = "Hook"
    CAT_STRUCTURE = "Structure"
    CAT_TIMING = "Timing"
    CAT_CTA = "CTA"
    CAT_TOPIC = "Topic"
    CAT_FAILURE = "Failure"
    CAT_META = "Meta"

    # Status options
    STATUS_ACTIVE = "Active"
    STATUS_TESTING = "Testing"
    STATUS_DEPRECATED = "Deprecated"

    # Operational rule titles (machine-parsed by Loop 1 from Active rows)
    RULE_DAILY_LIMIT = "Daily Limit"          # Rule Content = integer
    RULE_BEST_HOOK = "Best Hook"              # Rule Content = "A" / "B" / "C"
    RULE_BEST_SLOTS = "Best Slots"            # Rule Content = JSON array of slots
    RULE_BEST_CONTENT_TYPES = "Best Content Types"  # Rule Content = JSON array
    RULE_LEARN_SUMMARY = "LEARN Summary"      # Rule Content = human-readable prose
    # Per-platform winning hook (X vs Threads audiences differ). Loop 1 biases
    # each platform by its own winner; the pooled RULE_BEST_HOOK stays as a
    # fallback. Rule Content = "A" / "B" / "C".
    RULE_BEST_HOOK_X = "Best Hook (X)"
    RULE_BEST_HOOK_THREADS = "Best Hook (Threads)"
    RULE_BEST_HOOK_INSTAGRAM = "Best Hook (Instagram)"
    # Nightly follower snapshots. Rule Content = JSON {"YYYY-MM-DD": count} of
    # the most recent 90 days. Loop 2 reports deltas; Loop 1 ignores these.
    RULE_FOLLOWERS_X = "Follower History (X)"
    RULE_FOLLOWERS_THREADS = "Follower History (Threads)"
    RULE_FOLLOWERS_INSTAGRAM = "Follower History (Instagram)"
    # Written by Loop 1 when X returns 402 (monthly write quota exhausted);
    # Rule Content = ISO date until which X posting is parked. Deprecate or
    # delete the row in Notion to resume X earlier.
    RULE_X_PARKED = "X Parked Until"


# Hook key (A/B/C) -> (Content Drafts hook field, Performance "Hook Used" option)
HOOK_FIELDS = {
    "A": (Drafts.HOOK_A, Performance.HOOK_USED_A),
    "B": (Drafts.HOOK_B, Performance.HOOK_USED_B),
    "C": (Drafts.HOOK_C, Performance.HOOK_USED_C),
}
