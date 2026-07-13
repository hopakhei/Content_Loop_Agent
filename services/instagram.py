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
# Media-insight metric sets, tried in order — IG rejects the whole call if any
# single metric is unavailable for that media/API version, so we degrade from
# the richest set (with growth signals `saved`/`profile_visits` and the
# `views` impression proxy) down to a minimal one that always resolves.
INSIGHT_METRIC_SETS = (
    "views,reach,likes,comments,saved,shares,profile_visits",
    "reach,likes,comments,saved,shares",
    "reach,likes,comments",
)


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
        self._ok_metric_set: Optional[str] = None   # pinned after first insights success
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

    # ── insights (Loop 2) ────────────────────────────────────────────────────
    def get_follower_count(self) -> Optional[int]:
        """Loop 2 growth telemetry: current Instagram follower count. None on
        any failure — never raise (telemetry must not fail the run)."""
        if self.dry_run or self.session is None:
            return None
        try:
            uid = self._resolve_user_id()
            r = self.session.get(
                f"{API_BASE}/{uid}",
                params={"fields": "followers_count", "access_token": self.token},
                timeout=30,
            )
            r.raise_for_status()
            val = r.json().get("followers_count")
            return int(val) if val is not None else None
        except Exception as exc:
            self.log.warning("Instagram follower count unavailable: %s", _err_detail(exc))
            return None

    def get_insights(self, media_ids: list[str]) -> dict[str, dict[str, float]]:
        """Loop 2: per-media insights, normalized to the shared metric schema so
        the analysis treats IG like the other platforms:

            impressions ← views (fallback reach)   replies      ← comments
            likes       ← likes                     reposts      ← shares
            bookmarks   ← saved (growth signal)     profile_clicks ← profile_visits

        Returns {media_id: {metric: value}}. `bookmarks`/`profile_clicks` feed
        the same follower-growth proxy as X. Never raises — a failing media is
        skipped. The working metric set is remembered after the first success so
        later media don't re-probe the fallback ladder."""
        if self.dry_run or self.session is None or not media_ids:
            return {}
        out: dict[str, dict[str, float]] = {}
        failures = 0
        for mid in media_ids:
            vals = self._media_insight_values(mid)
            if vals is None:
                failures += 1
                if failures == 1:
                    self.log.warning("Instagram insights failed for %s — check the token scope.", mid)
                if failures >= 3 and not out:
                    self.log.warning("Instagram insights failing consistently — skipping the rest.")
                    break
                continue
            out[mid] = {
                "impressions": vals.get("views", vals.get("reach", 0)),
                "likes": vals.get("likes", 0),
                "replies": vals.get("comments", 0),
                "reposts": vals.get("shares", 0),
                "bookmarks": vals.get("saved", 0),
                "profile_clicks": vals.get("profile_visits", 0),
            }
        return out

    def _media_insight_values(self, media_id: str) -> Optional[dict]:
        """GET one media's insights, degrading through INSIGHT_METRIC_SETS until
        a set resolves. Returns {metric_name: value} or None if all sets fail.
        The first set that works is pinned for the rest of the run."""
        sets = (self._ok_metric_set,) if self._ok_metric_set else INSIGHT_METRIC_SETS
        for metric in sets:
            try:
                r = self.session.get(
                    f"{API_BASE}/{media_id}/insights",
                    params={"metric": metric, "access_token": self.token},
                    timeout=30,
                )
                r.raise_for_status()
            except Exception:
                continue
            self._ok_metric_set = metric
            return {item.get("name"): _insight_value(item) for item in r.json().get("data", [])}
        return None

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


def _insight_value(item: dict) -> float:
    """IG insights come back as either total_value or a values[] series."""
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
        except Exception:  # pragma: no cover - defensive
            pass
    return str(exc)
