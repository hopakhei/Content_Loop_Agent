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

# Include the CTA link on X? On by default now — the CTA is just a bare link
# (no sell copy). Set false to post X link-free (max reach, no link
# suppression) when growing followers matters more than the funnel; Threads
# keeps the link regardless.
X_INCLUDE_CTA = _flag("X_INCLUDE_CTA", True)
# Each tweet in a chain costs one write from the monthly credit budget, so a
# 6-tweet thread = 6 posts' worth. Cap X at the root tweet by default — the
# full chain still goes out on Threads (whose API is free).
X_MAX_THREAD_POSTS = _int("X_MAX_THREAD_POSTS", 1)
# Randomized per-post X link A/B: when on (and X_INCLUDE_CTA is on), each X
# post flips a fair coin between carrying its link and going link-free, tagged
# on the Performance row so Loop 2 measures the reach cost cleanly instead of
# guessing. Set false to stop the experiment.
X_LINK_AB = _flag("X_LINK_AB", True)
# Free-tier monthly write allowance, for the LEARN budget telemetry.
X_MONTHLY_WRITE_BUDGET = _int("X_MONTHLY_WRITE_BUDGET", 500)


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
