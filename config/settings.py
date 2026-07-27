"""Central configuration: environment variables, limits and the posting schedule.

All values are read once at import time. Secrets come from the environment
(loaded from `.env` in local/dev via python-dotenv); nothing secret is hard-coded.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

try:  # python-dotenv is optional at runtime (cron may inject env directly)
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - dotenv missing is fine
    pass


BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "logs"
PROMPTS_DIR = BASE_DIR / "prompts"


def _flag(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


# ── Notion ──────────────────────────────────────────────────────────────────
NOTION_TOKEN = os.getenv("NOTION_TOKEN", "").strip()
NOTION_ARTICLE_LIBRARY_DB = os.getenv("NOTION_ARTICLE_LIBRARY_DB", "").strip()
NOTION_CONTENT_DRAFTS_DB = os.getenv("NOTION_CONTENT_DRAFTS_DB", "").strip()
NOTION_PERFORMANCE_LOG_DB = os.getenv("NOTION_PERFORMANCE_LOG_DB", "").strip()
NOTION_AGENT_RULES_DB = os.getenv("NOTION_AGENT_RULES_DB", "").strip()

# ── X / Twitter ─────────────────────────────────────────────────────────────
X_API_KEY = os.getenv("X_API_KEY", "").strip()
X_API_SECRET = os.getenv("X_API_SECRET", "").strip()
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN", "").strip()
X_ACCESS_SECRET = os.getenv("X_ACCESS_SECRET", "").strip()
X_BEARER_TOKEN = os.getenv("X_BEARER_TOKEN", "").strip()

# Include the CTA link on X? Off by default — X posts go link-free: links cost
# 30-50% reach (zero median engagement for free accounts) and a CTA tweet in a
# chain burns an extra write from the 17-posts/24h free-tier quota. Threads
# keeps the link regardless. Set true to restore links on X.
X_INCLUDE_CTA = _flag("X_INCLUDE_CTA", False)
# Max tweets per X thread. Each chained tweet costs one write from the free-tier
# quota (17/24h, 500/month), but a root-only thread reads as half a thought, so
# post the full chain. Lower this if the write quota starts 402/429-ing.
X_MAX_THREAD_POSTS = _int("X_MAX_THREAD_POSTS", 10)
# Post the whole framework as ONE X post instead of a reply chain. X Premium
# allows up to 25,000 chars, so a single long post carries the full argument
# while spending only one write from the quota (a chain burns one per segment).
# The composed segments are joined with blank lines into that single post.
# Threads still ships the full multi-part chain. Set false to chain on X too.
X_LONGPOST = _flag("X_LONGPOST", True)
# Char ceiling for a single X long post (Premium is 25,000). Used only as the
# length-warning limit when X_LONGPOST is on.
X_LONGPOST_LIMIT = _int("X_LONGPOST_LIMIT", 25000)
# Randomized per-post X link A/B: when on (and X_INCLUDE_CTA is on), each X
# post flips a fair coin between carrying its link and going link-free, tagged
# on the Performance row so Loop 2 measures the reach cost cleanly instead of
# guessing. Set false to stop the experiment.
X_LINK_AB = _flag("X_LINK_AB", True)
# Free-tier monthly write allowance, for the LEARN budget telemetry.
X_MONTHLY_WRITE_BUDGET = _int("X_MONTHLY_WRITE_BUDGET", 500)
# Strategy pivot: promote the consulting-framework series on X/Threads and pause
# the numbered personal essays (101–201, 127…). Post loop then only posts drafts
# whose issue is a non-numeric slug (framework units). Set false to resume essays.
POST_FRAMEWORKS_ONLY = _flag("POST_FRAMEWORKS_ONLY", True)


def _json_map(name: str, default: dict) -> dict:
    raw = os.getenv(name, "").strip()
    if not raw:
        return dict(default)
    try:
        val = json.loads(raw)
        return {str(k): str(v) for k, v in val.items()} if isinstance(val, dict) else dict(default)
    except ValueError:
        return dict(default)


# Per-issue CTA override applied ONLY on X ({"issue": "url"}). X suppresses
# Substack links harder than most domains, and the build-in-public pieces have
# a natural X-native destination (the GitHub repo) — Threads keeps the
# article's own CTA. Override via the X_CTA_BY_ISSUE env var (JSON).
X_CTA_BY_ISSUE = _json_map("X_CTA_BY_ISSUE", {
    "201": "https://github.com/Draw-Tree/tree-quant-ledger",
})

# ── Threads (Meta) ──────────────────────────────────────────────────────────
THREADS_ACCESS_TOKEN = os.getenv("THREADS_ACCESS_TOKEN", "").strip()
THREADS_USER_ID = os.getenv("THREADS_USER_ID", "").strip()

# ── Instagram (Meta) — optional; posts Quote Cards as image cards ────────────
IG_ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN", "").strip()
IG_USER_ID = os.getenv("IG_USER_ID", "").strip()          # auto-resolved from /me
# Public base URL where committed cards/ PNGs are reachable (IG's media create
# needs a public image_url). instagram.yml sets this from the repo + branch.
IG_CARD_URL_BASE = os.getenv("IG_CARD_URL_BASE", "").strip()
# IG bio holds the Substack link (caption links aren't clickable); this line is
# appended to the caption.
IG_CTA_LINE = os.getenv("IG_CTA_LINE", "完整框架在 Substack，連結見 bio 🔗").strip()
# Hashtags appended to the IG caption (IG rewards them, unlike X).
IG_HASHTAGS = os.getenv("IG_HASHTAGS", "#投資 #價值投資 #財經 #stockmarket").strip()

# ── Instagram comment-to-DM ─────────────────────────────────────────────────
# A comment containing IG_DM_KEYWORD triggers ONE private reply carrying the
# post's article link — the only automated path to a TAPPABLE IG link. Needs
# instagram_business_manage_comments + instagram_business_manage_messages.
# Comma-separated; a comment containing ANY of them triggers the reply. It has
# to be a list: captions have asked for 「全文」 on the essay carousels and
# 「框架」 on the framework series, and a single-keyword setting silently
# ignored every comment on the newer half.
IG_DM_KEYWORDS = [
    k.strip() for k in os.getenv("IG_DM_KEYWORD", "全文,框架,案例").split(",") if k.strip()
]
# Kept for logs and older call sites.
IG_DM_KEYWORD = ", ".join(IG_DM_KEYWORDS)
# DM every comment instead of keyword-matches only (aggressive; default off).
IG_DM_ALL = _flag("IG_DM_ALL", False)
# {url} is replaced with the post's article link.
IG_DM_TEXT = os.getenv(
    "IG_DM_TEXT",
    "謝謝留言 🙏 這裡是用這些策略框架拆真實公司的案例，整個系列都在裡面：{url}",
).strip()
# When a post carries no per-article link tag, DM this instead.
IG_DM_FALLBACK_URL = os.getenv(
    "IG_DM_FALLBACK_URL", "https://90spminvesting.substack.com/?r=25kdss"
).strip()
# Per-run send cap — spam brake.
IG_DM_MAX_PER_RUN = _int("IG_DM_MAX_PER_RUN", 20)

# ── Claude (Loop 3) ─────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
# `or` (not a getenv default) so a set-but-empty env var still falls back.
CLAUDE_MODEL = (os.getenv("CLAUDE_MODEL") or "claude-opus-4-8").strip()

# ── Behaviour ───────────────────────────────────────────────────────────────
MAX_POSTS_PER_RUN = _int("MAX_POSTS_PER_RUN", 1)
DAILY_HARD_LIMIT = _int("DAILY_HARD_LIMIT", 5)
PREVIEW_COUNTDOWN_SECONDS = _int("PREVIEW_COUNTDOWN_SECONDS", 5)
DRY_RUN = _flag("DRY_RUN", False)
TZ_NAME = os.getenv("TZ_NAME", "Asia/Hong_Kong").strip() or "Asia/Hong_Kong"

POST_SLOTS_HKT = [
    s.strip()
    for s in os.getenv("POST_SLOTS_HKT", "07:30,10:00,12:30,18:30,21:30").split(",")
    if s.strip()
]
