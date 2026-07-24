"""X (Twitter) API v2 wrapper.

Posts single tweets and threads, and reads public engagement metrics for Loop 2.
In `dry_run` mode nothing hits the network — `post_*` returns deterministic
fake ids prefixed `DRYRUN-` so the rest of the pipeline can be exercised safely.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from config import settings
from services.errors import PartialThreadError

try:
    import tweepy
except ImportError:  # pragma: no cover - surfaced at runtime with a clear message
    tweepy = None


class TwitterService:
    def __init__(self, dry_run: bool = False, logger: Optional[logging.Logger] = None, client=None):
        self.dry_run = dry_run
        self.log = logger or logging.getLogger("loop.twitter")
        self._dry_counter = 0
        if client is not None:
            self.client = client
        elif dry_run:
            self.client = None
        else:
            if tweepy is None:
                raise RuntimeError("tweepy is not installed. `pip install -r requirements.txt`")
            missing = [
                name
                for name, val in {
                    "X_API_KEY": settings.X_API_KEY,
                    "X_API_SECRET": settings.X_API_SECRET,
                    "X_ACCESS_TOKEN": settings.X_ACCESS_TOKEN,
                    "X_ACCESS_SECRET": settings.X_ACCESS_SECRET,
                }.items()
                if not val
            ]
            if missing:
                raise RuntimeError(f"Missing X API credentials: {', '.join(missing)}")
            self.client = tweepy.Client(
                consumer_key=settings.X_API_KEY,
                consumer_secret=settings.X_API_SECRET,
                access_token=settings.X_ACCESS_TOKEN,
                access_token_secret=settings.X_ACCESS_SECRET,
                bearer_token=settings.X_BEARER_TOKEN or None,
            )

    def post_tweet(self, text: str, in_reply_to: Optional[str] = None) -> str:
        if self.dry_run:
            self._dry_counter += 1
            stamp = datetime.now(timezone.utc).strftime("%H%M%S")
            fake = f"DRYRUN-{stamp}-{self._dry_counter}"
            self.log.info("[dry-run] would post tweet (reply_to=%s): %s", in_reply_to, _preview(text))
            return fake
        resp = self.client.create_tweet(text=text, in_reply_to_tweet_id=in_reply_to)
        return str(resp.data["id"])

    def post_thread(self, tweets: list[str]) -> list[str]:
        """Post tweets as a reply chain. Returns the ids in order; ids[0] is the
        root tweet (the canonical Post ID for Performance logging).

        If the chain fails midway, raises PartialThreadError carrying the ids
        that DID post — the root tweet is live, so the caller must record it
        rather than retry the whole thread (X rejects duplicate content anyway).
        """
        ids: list[str] = []
        reply_to: Optional[str] = None
        for text in tweets:
            try:
                tid = self.post_tweet(text, in_reply_to=reply_to)
            except Exception as exc:
                if ids:
                    raise PartialThreadError(ids, exc) from exc
                raise
            ids.append(tid)
            reply_to = tid
        return ids

    def verify(self) -> str:
        """Read-only credential check: confirm user-context OAuth works (does NOT
        post). Returns the authenticated @handle; raises if the creds are invalid."""
        if self.client is None:
            raise RuntimeError("No X client (constructed in dry-run without credentials).")
        me = self.client.get_me()
        data = getattr(me, "data", None)
        return getattr(data, "username", None) or "unknown"

    def get_follower_count(self) -> Optional[int]:
        """Loop 2 growth telemetry: current follower count (1 read/day). None on
        any failure — never raise into the nightly run."""
        if self.dry_run or self.client is None:
            return None
        try:
            me = self.client.get_me(user_fields=["public_metrics"], user_auth=True)
            pm = getattr(getattr(me, "data", None), "public_metrics", None) or {}
            return pm.get("followers_count")
        except Exception as exc:
            self.log.warning("X follower count unavailable: %s", exc)
            return None

    def get_metrics(self, tweet_ids: list[str]) -> dict[str, dict[str, float]]:
        """Loop 2: fetch engagement for own tweets. Returns {id: {metric: value}}.

        `public_metrics` (likes/replies/reposts/quotes) are always available;
        `non_public_metrics` (impressions, url link clicks) require user-context
        auth — `user_auth=True`, or the API rejects the request — and only exist
        for your own tweets from the last 30 days. If that request is rejected
        (e.g. access-tier limits) we degrade to public metrics only, and the
        impressions/link_clicks keys are omitted so existing Notion values are
        preserved rather than zeroed.
        """
        if self.dry_run or not tweet_ids:
            return {}
        out: dict[str, dict[str, float]] = {}
        for i in range(0, len(tweet_ids), 100):  # lookup accepts at most 100 ids
            resp = self._lookup_tweets(tweet_ids[i:i + 100])
            if resp is None:
                continue
            for tw in resp.data or []:
                pm = getattr(tw, "public_metrics", None) or {}
                m: dict[str, float] = {
                    "likes": pm.get("like_count", 0),
                    "replies": pm.get("reply_count", 0),
                    "reposts": pm.get("retweet_count", 0),
                    "quotes": pm.get("quote_count", 0),
                    "bookmarks": pm.get("bookmark_count", 0),  # follow/reference proxy
                }
                npm = getattr(tw, "non_public_metrics", None) or {}
                if npm:
                    m["impressions"] = npm.get("impression_count", 0)
                    m["link_clicks"] = npm.get("url_link_clicks", 0)
                org = getattr(tw, "organic_metrics", None) or {}
                if org:
                    m["profile_clicks"] = org.get("user_profile_clicks", 0)
                    m.setdefault("impressions", org.get("impression_count", 0))
                out[str(tw.id)] = m
        return out

    # tweet_fields tried in order; the first that the tier accepts wins. Each is
    # a superset drop of the previous — organic_metrics (profile clicks) is the
    # richest and the most likely to be rejected on the free tier.
    _METRIC_FIELD_SETS = (
        ["public_metrics", "non_public_metrics", "organic_metrics"],
        ["public_metrics", "non_public_metrics"],
        ["public_metrics"],
    )

    def _lookup_tweets(self, ids: list[str]):
        last_exc = None
        for fields in self._METRIC_FIELD_SETS:
            try:
                return self.client.get_tweets(ids=ids, tweet_fields=fields, user_auth=True)
            except Exception as exc:
                last_exc = exc
                self.log.warning("Tweet lookup %s rejected (%s) — trying a smaller field set.", fields, exc)
        self.log.warning("Tweet metrics lookup failed for %d ids: %s", len(ids), last_exc)
        return None


def _preview(text: str, limit: int = 80) -> str:
    flat = text.replace("\n", " ⏎ ")
    return flat if len(flat) <= limit else flat[:limit] + "…"
