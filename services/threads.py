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
from datetime import datetime, timezone
from typing import Optional

from config import settings

try:
    import requests
except ImportError:  # pragma: no cover - surfaced at runtime
    requests = None

API_BASE = "https://graph.threads.net/v1.0"
MAX_POST_LEN = 500  # Threads text limit


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

        r2 = self.session.post(
            f"{API_BASE}/{uid}/threads_publish",
            data={"creation_id": creation_id, "access_token": self.token},
            timeout=30,
        )
        r2.raise_for_status()
        return str(r2.json()["id"])

    def post_thread(self, posts: list[str]) -> list[str]:
        """Post a reply chain. Returns ids in order; ids[0] is the root post
        (the canonical Post ID for Performance logging)."""
        ids: list[str] = []
        reply_to: Optional[str] = None
        for text in posts:
            pid = self.post_post(text, reply_to=reply_to)
            ids.append(pid)
            reply_to = pid
        return ids


def _preview(text: str, limit: int = 80) -> str:
    flat = text.replace("\n", " ⏎ ")
    return flat if len(flat) <= limit else flat[:limit] + "…"
