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
        root tweet (the canonical Post ID for Performance logging)."""
        ids: list[str] = []
        reply_to: Optional[str] = None
        for text in tweets:
            tid = self.post_tweet(text, in_reply_to=reply_to)
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

    def get_metrics(self, tweet_ids: list[str]) -> dict[str, dict[str, float]]:
        """Loop 2: fetch engagement for own tweets. Returns {id: {metric: value}}.

        `public_metrics` (likes/replies/reposts/quotes) are always available;
        `non_public_metrics` (impressions, url link clicks) require user-context
        auth and are only returned for your own recent tweets.
        """
        if self.dry_run or not tweet_ids:
            return {}
        out: dict[str, dict[str, float]] = {}
        resp = self.client.get_tweets(
            ids=tweet_ids,
            tweet_fields=["public_metrics", "non_public_metrics"],
        )
        for tw in resp.data or []:
            pm = getattr(tw, "public_metrics", None) or {}
            npm = getattr(tw, "non_public_metrics", None) or {}
            out[str(tw.id)] = {
                "likes": pm.get("like_count", 0),
                "replies": pm.get("reply_count", 0),
                "reposts": pm.get("retweet_count", 0),
                "quotes": pm.get("quote_count", 0),
                "impressions": npm.get("impression_count", 0),
                "link_clicks": npm.get("url_link_clicks", 0),
            }
        return out


def _preview(text: str, limit: int = 80) -> str:
    flat = text.replace("\n", " ⏎ ")
    return flat if len(flat) <= limit else flat[:limit] + "…"
