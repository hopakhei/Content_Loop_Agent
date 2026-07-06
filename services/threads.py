"""Threads (Meta) publisher.

Posts single posts and reply-chains via the official Threads API
(https://developers.facebook.com/docs/threads). Publishing is two-step:
create a media container, then publish it. Replies chain with `reply_to_id`.

Auth is a long-lived Threads user access token (THREADS_ACCESS_TOKEN, ~60 days,
refreshable). THREADS_USER_ID is optional — resolved from /me when absent.
In `dry_run` mode nothing hits the network; fake ids are prefixed `DRYRUN-`.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from config import settings
from services.errors import PartialThreadError

try:
    import requests
except ImportError:  # pragma: no cover - surfaced at runtime
    requests = None

API_BASE = "https://graph.threads.net/v1.0"
MAX_POST_LEN = 500  # Threads text limit
# threads_publish intermittently 500s right after container creation; retry
# with these delays before giving up. (Tests shrink this to avoid sleeping.)
PUBLISH_RETRY_DELAYS = (2.0, 5.0)


class ThreadsService:
    def __init__(
        self,
        dry_run: bool = False,
        logger: Optional[logging.Logger] = None,
        session=None,
        access_token: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        self.dry_run = dry_run
        self.log = logger or logging.getLogger("loop.threads")
        self.token = access_token or settings.THREADS_ACCESS_TOKEN
        self.user_id = user_id or settings.THREADS_USER_ID
        self._dry_counter = 0
        if session is not None:
            self.session = session
        elif dry_run:
            self.session = None
        else:
            if requests is None:
                raise RuntimeError("requests is not installed. `pip install -r requirements.txt`")
            if not self.token:
                raise RuntimeError("THREADS_ACCESS_TOKEN is not set.")
            self.session = requests.Session()

    # ── auth / identity ──────────────────────────────────────────────────────
    def _me(self) -> dict:
        r = self.session.get(
            f"{API_BASE}/me",
            params={"fields": "id,username", "access_token": self.token},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def _resolve_user_id(self) -> str:
        if not self.user_id:
            self.user_id = self._me()["id"]
        return self.user_id

    def verify(self) -> str:
        """Read-only credential check. Returns the authenticated @handle."""
        if self.session is None:
            raise RuntimeError("No Threads session (constructed in dry-run without credentials).")
        data = self._me()
        self.user_id = data.get("id", self.user_id)
        return data.get("username") or "unknown"

    # ── publishing ───────────────────────────────────────────────────────────
    def post_post(self, text: str, reply_to: Optional[str] = None) -> str:
        if self.dry_run:
            self._dry_counter += 1
            stamp = datetime.now(timezone.utc).strftime("%H%M%S")
            fake = f"DRYRUN-TH-{stamp}-{self._dry_counter}"
            self.log.info("[dry-run] would post to Threads (reply_to=%s): %s", reply_to, _preview(text))
            return fake

        uid = self._resolve_user_id()
        payload = {"media_type": "TEXT", "text": text, "access_token": self.token}
        if reply_to:
            payload["reply_to_id"] = reply_to
        r = self.session.post(f"{API_BASE}/{uid}/threads", data=payload, timeout=30)
        r.raise_for_status()
        creation_id = r.json()["id"]
        return self._publish(uid, creation_id)

    def _publish(self, uid: str, creation_id: str) -> str:
        """Publish a created container, retrying transient (5xx) server errors."""
        for attempt, delay in enumerate((0.0,) + tuple(PUBLISH_RETRY_DELAYS)):
            if delay:
                time.sleep(delay)
            r = self.session.post(
                f"{API_BASE}/{uid}/threads_publish",
                data={"creation_id": creation_id, "access_token": self.token},
                timeout=30,
            )
            status = getattr(r, "status_code", 200)
            if status >= 500 and attempt < len(PUBLISH_RETRY_DELAYS):
                self.log.warning(
                    "threads_publish returned %s (attempt %d) — retrying.", status, attempt + 1
                )
                continue
            r.raise_for_status()
            return str(r.json()["id"])
        raise RuntimeError("unreachable")  # pragma: no cover

    def post_thread(self, posts: list[str]) -> list[str]:
        """Post a reply chain. Returns ids in order; ids[0] is the root post
        (the canonical Post ID for Performance logging).

        If the chain fails midway, raises PartialThreadError carrying the ids
        that DID post — the root post is live, so the caller must record it
        rather than retry the whole thread.
        """
        ids: list[str] = []
        reply_to: Optional[str] = None
        for text in posts:
            try:
                pid = self.post_post(text, reply_to=reply_to)
            except Exception as exc:
                if ids:
                    raise PartialThreadError(ids, exc) from exc
                raise
            ids.append(pid)
            reply_to = pid
        return ids

    # ── insights (Loop 2) ────────────────────────────────────────────────────
    def get_insights(self, post_ids: list[str]) -> dict[str, dict[str, float]]:
        """Loop 2: lifetime insights per post. Returns {id: {metric: value}}
        with Threads `views` mapped to `impressions` (link clicks don't exist
        on Threads). Requires the token to carry the `threads_manage_insights`
        scope — regenerate THREADS_ACCESS_TOKEN with that scope checked if
        every call fails with a permission error.
        """
        if self.dry_run or not post_ids:
            return {}
        out: dict[str, dict[str, float]] = {}
        failures = 0
        for pid in post_ids:
            try:
                r = self.session.get(
                    f"{API_BASE}/{pid}/insights",
                    params={"metric": "views,likes,replies,reposts,quotes", "access_token": self.token},
                    timeout=30,
                )
                r.raise_for_status()
                vals = {item.get("name"): _insight_value(item) for item in r.json().get("data", [])}
            except Exception as exc:
                failures += 1
                if failures == 1:
                    self.log.warning(
                        "Threads insights failed for %s: %s — if this is a permission error, "
                        "regenerate THREADS_ACCESS_TOKEN with the threads_manage_insights scope.",
                        pid, _err_detail(exc),
                    )
                if failures >= 3 and not out:
                    self.log.warning("Threads insights failing consistently — skipping the remaining posts.")
                    break
                continue
            out[pid] = {
                "impressions": vals.get("views", 0),
                "likes": vals.get("likes", 0),
                "replies": vals.get("replies", 0),
                "reposts": vals.get("reposts", 0),
                "quotes": vals.get("quotes", 0),
            }
        return out


def _insight_value(item: dict) -> float:
    """Insights come back as either total_value or a values[] series."""
    tv = item.get("total_value")
    if isinstance(tv, dict) and "value" in tv:
        return tv["value"]
    vals = item.get("values") or []
    return (vals[0] or {}).get("value", 0) if vals else 0


def _err_detail(exc: Exception) -> str:
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            return f"{exc} | {resp.text[:200]}"
        except Exception:
            pass
    return str(exc)


def _preview(text: str, limit: int = 80) -> str:
    flat = text.replace("\n", " ⏎ ")
    return flat if len(flat) <= limit else flat[:limit] + "…"
