"""Instagram (Meta) image publisher — the Instagram API with Instagram Login.

Publishing is two-step, like Threads: create a media container from a PUBLIC
`image_url` (+ caption), wait until it reports FINISHED, then publish it. Auth
is a long-lived Instagram user access token (IG_ACCESS_TOKEN); IG_USER_ID is
resolved from /me when blank. `dry_run` never touches the network. P2 of
docs/instagram-plan.md.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

from config import settings

try:
    import requests
except ImportError:  # pragma: no cover - surfaced at runtime
    requests = None

API_BASE = "https://graph.instagram.com/v21.0"
MAX_CAPTION_LEN = 2200
PUBLISH_RETRY_DELAYS = (2.0, 5.0)
# IG media containers take a moment to finish processing before they publish.
CONTAINER_READY_DELAYS = (1.0, 2.0, 3.0, 5.0, 8.0)


class InstagramService:
    def __init__(
        self,
        dry_run: bool = False,
        logger: Optional[logging.Logger] = None,
        session=None,
        access_token: Optional[str] = None,
        user_id: Optional[str] = None,
    ):
        self.dry_run = dry_run
        self.log = logger or logging.getLogger("loop.instagram")
        self.token = access_token or settings.IG_ACCESS_TOKEN
        self.user_id = user_id or settings.IG_USER_ID
        self._dry_counter = 0
        if session is not None:
            self.session = session
        elif dry_run:
            self.session = None
        else:
            if requests is None:
                raise RuntimeError("requests is not installed. `pip install -r requirements.txt`")
            if not self.token:
                raise RuntimeError("IG_ACCESS_TOKEN is not set.")
            self.session = requests.Session()

    # ── auth / identity ──────────────────────────────────────────────────────
    def _me(self) -> dict:
        r = self.session.get(
            f"{API_BASE}/me",
            params={"fields": "user_id,username", "access_token": self.token},
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def _resolve_user_id(self) -> str:
        if not self.user_id:
            data = self._me()
            self.user_id = str(data.get("user_id") or data.get("id"))
        return self.user_id

    def verify(self) -> str:
        """Read-only credential check. Returns the authenticated @handle."""
        if self.session is None:
            raise RuntimeError("No Instagram session (dry-run without credentials).")
        data = self._me()
        self.user_id = str(data.get("user_id") or data.get("id") or self.user_id)
        return data.get("username") or "unknown"

    # ── publishing ───────────────────────────────────────────────────────────
    def publish_image(self, image_url: str, caption: str) -> str:
        """Create a media container from a public image_url and publish it.
        Returns the published media id."""
        caption = (caption or "")[:MAX_CAPTION_LEN]
        if self.dry_run:
            self._dry_counter += 1
            stamp = datetime.now(timezone.utc).strftime("%H%M%S")
            self.log.info("[dry-run] would post to Instagram: %s | %s", image_url, _preview(caption))
            return f"DRYRUN-IG-{stamp}-{self._dry_counter}"

        uid = self._resolve_user_id()
        create = self._post_with_retry(
            f"{API_BASE}/{uid}/media",
            {"image_url": image_url, "caption": caption, "access_token": self.token},
            what="create container",
        )
        creation_id = create.json()["id"]
        self._await_container(creation_id)
        publish = self._post_with_retry(
            f"{API_BASE}/{uid}/media_publish",
            {"creation_id": creation_id, "access_token": self.token},
            what="publish",
            retry_client_errors=True,
        )
        return str(publish.json()["id"])

    def _await_container(self, creation_id: str) -> None:
        """Poll until IG reports the container FINISHED. Best-effort: a failed
        status check falls through to publish; a terminal ERROR/EXPIRED raises."""
        for delay in CONTAINER_READY_DELAYS:
            if delay:
                time.sleep(delay)
            try:
                r = self.session.get(
                    f"{API_BASE}/{creation_id}",
                    params={"fields": "status_code,status", "access_token": self.token},
                    timeout=30,
                )
                r.raise_for_status()
                data = r.json()
            except Exception as exc:
                self.log.warning("IG container status check failed (%s) — proceeding to publish.", exc)
                return
            status = (data.get("status_code") or "").upper()
            if status in ("FINISHED", "PUBLISHED", ""):
                return
            if status in ("ERROR", "EXPIRED"):
                raise RuntimeError(f"IG container {status}: {data.get('status') or 'no detail from Meta'}")
        self.log.warning("IG container %s still IN_PROGRESS after polling — attempting publish anyway.", creation_id)

    def _post_with_retry(self, url: str, data: dict, *, what: str, retry_client_errors: bool = False):
        """POST to a graph endpoint, retrying transient failures (5xx or network;
        also 4xx when `retry_client_errors`) with backoff. Error messages carry
        the response body for diagnosis."""
        last_detail = None
        for attempt, delay in enumerate((0.0,) + tuple(PUBLISH_RETRY_DELAYS)):
            more = attempt < len(PUBLISH_RETRY_DELAYS)
            if delay:
                time.sleep(delay)
            try:
                r = self.session.post(url, data=data, timeout=30)
            except Exception as exc:  # network error
                if not more:
                    raise
                self.log.warning("IG %s network error (attempt %d): %s — retrying.", what, attempt + 1, exc)
                continue
            status = getattr(r, "status_code", 200)
            if status < 400:
                return r
            last_detail = f"{status} {_body_snippet(r)}".strip()
            if more and (status >= 500 or retry_client_errors):
                self.log.warning("IG %s returned %s (attempt %d) — retrying.", what, last_detail, attempt + 1)
                continue
            break
        raise RuntimeError(f"IG {what} failed: {last_detail}")


def _preview(text: str, limit: int = 80) -> str:
    flat = (text or "").replace("\n", " ⏎ ")
    return flat if len(flat) <= limit else flat[:limit] + "…"


def _body_snippet(resp) -> str:
    try:
        return (getattr(resp, "text", "") or "")[:200]
    except Exception:  # pragma: no cover - defensive
        return ""
