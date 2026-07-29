"""Instagram comment-to-DM.

Polls comments on our recent IG media; a comment containing IG_DM_KEYWORD
(or any comment, with IG_DM_ALL) gets ONE private reply carrying that post's
article link — links are tappable in DMs, unlike captions/comments/bio-less
surfaces. Runs from instagram-dm.yml on a short cron; the private-reply API
allows one reply per comment within 7 days, so polling latency is fine.

Idempotency: every comment id we have seen is recorded in a state file that
the workflow commits back, so nobody is ever DM'd twice. Our own comments
(the auto first-comment) are skipped by username.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from config import settings
from services.instagram import InstagramService
from services.notion import NotionService

STATE_FILE = "state/ig_dm_state.json"
# Readers describing, in their own words, what they wanted from a post — the
# best available source of hypotheses, and until now read once for a keyword
# match and thrown away. Appended here so research/observations.md has
# something to draw on that is not our own metrics. Committed by the workflow
# alongside the state file.
COMMENT_LOG = "research/audience/ig_comments.jsonl"
# Private replies are only accepted within 7 days of the comment; leave margin.
REPLY_WINDOW_HOURS = 7 * 24 - 2
# Keep handled ids this long before trimming (well past the reply window).
STATE_RETENTION_DAYS = 30


def run(
    dry_run: bool = False,
    logger: Optional[logging.Logger] = None,
    notion: Optional[NotionService] = None,
    ig: Optional[InstagramService] = None,
    state_file: str = STATE_FILE,
    comment_log: str = COMMENT_LOG,
    now: Optional[datetime] = None,
) -> dict:
    log = logger or logging.getLogger("loop.igdm")
    if ig is None:
        if not settings.IG_ACCESS_TOKEN:
            log.info("IG_ACCESS_TOKEN not set — skipping comment-to-DM.")
            return {"sent": 0, "skipped": "no-token"}
        # Reads stay real even on --dry-run (so a dry run proves the scopes);
        # only the sends are gated below.
        ig = InstagramService(dry_run=False, logger=log)
    now = now or datetime.now(timezone.utc)

    try:
        me = ig.verify()
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status is not None and status >= 500:
            # Meta-side outage: nothing actionable, next cron tick retries.
            # 4xx (token/permission problems) still propagates and fails the run.
            log.warning("IG /me returned %s — Graph outage, skipping this cycle.", status)
            return {"sent": 0, "skipped": f"graph-{status}"}
        raise
    state = _load_state(state_file)
    handled = state["handled"]
    links = _media_links(notion or NotionService(log), log)

    media = ig.get_recent_media()
    log.info("comment-to-DM | media=%d | keyword=%r | all=%s | dry_run=%s",
             len(media), settings.IG_DM_KEYWORD, settings.IG_DM_ALL, dry_run)

    sent = matched = seen = 0
    captured: list[dict] = []
    for m in media:
        try:
            comments = ig.get_comments(m["id"])
        except Exception as exc:
            log.warning("comments unreadable for media %s: %s", m["id"], exc)
            continue
        for c in comments:
            cid = c.get("id")
            if not cid or cid in handled:
                continue
            seen += 1
            if (c.get("username") or "") == me:
                handled[cid] = now.isoformat()          # our own first comment
                continue
            # Capture before the keyword gate: the comments that do NOT ask for
            # the link are the ones worth reading, and they were exactly the
            # ones being discarded.
            captured.append({
                "id": cid,
                "media_id": m["id"],
                "at": c.get("timestamp"),
                "text": c.get("text") or "",
                "matched": _matches(c.get("text") or ""),
            })
            if not _matches(c.get("text") or ""):
                handled[cid] = now.isoformat()          # seen, not a trigger
                continue
            matched += 1
            if _age_hours(c.get("timestamp"), now) > REPLY_WINDOW_HOURS:
                log.info("comment %s past the 7d reply window — skipping.", cid)
                handled[cid] = now.isoformat()
                continue
            if sent >= settings.IG_DM_MAX_PER_RUN:
                log.warning("per-run DM cap (%d) reached — the rest wait for the next run.",
                            settings.IG_DM_MAX_PER_RUN)
                break
            url = links.get(m["id"]) or settings.IG_DM_FALLBACK_URL
            text = settings.IG_DM_TEXT.format(url=url)
            if dry_run:
                log.info("[dry-run] would DM @%s (comment %s): %s",
                         c.get("username"), cid, text)
                continue                                 # not marked — real run sends
            if ig.send_private_reply(cid, text):
                sent += 1
                log.info("DM ✓ @%s (comment on %s)", c.get("username"), m["id"])
            handled[cid] = now.isoformat()               # one attempt per comment

    if not dry_run:
        _save_state(state_file, state, now)
        _append_comments(comment_log, captured, log)
    log.info("comment-to-DM done | new comments=%d | matched=%d | sent=%d | logged=%d",
             seen, matched, sent, len(captured))
    return {"sent": sent, "matched": matched, "seen": seen, "captured": len(captured)}


def _append_comments(path: str, rows: list[dict], log) -> None:
    """Append-only JSONL. Never rewritten: a log that gets tidied stops being
    evidence of what readers actually said."""
    if not rows:
        return
    try:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            for row in rows:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        log.info("Logged %d comment(s) → %s", len(rows), path)
    except OSError as exc:
        # Never fail a DM run over the research log.
        log.warning("Could not write the comment log: %s", exc)


def _matches(text: str) -> bool:
    if settings.IG_DM_ALL:
        return True
    body = (text or "").casefold()
    return any(k.casefold() in body for k in settings.IG_DM_KEYWORDS)


def _age_hours(iso_ts: Optional[str], now: datetime) -> float:
    if not iso_ts:
        return 0.0
    try:
        ts = datetime.fromisoformat(iso_ts.replace("+0000", "+00:00").replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    return (now - ts).total_seconds() / 3600


def _media_links(notion: NotionService, log) -> dict:
    """{media_id: article link} from the Instagram Performance rows' `cta`
    tag. Best-effort — a miss falls back to IG_DM_FALLBACK_URL."""
    out: dict = {}
    try:
        for r in notion.get_performance_rows(since_days=30):
            if r.get("platform") != "Instagram":
                continue
            cta = (r.get("tags") or {}).get("cta")
            if r.get("post_id") and cta:
                out[r["post_id"]] = cta
    except Exception as exc:
        log.warning("media→link map unavailable (%s); using the fallback URL.", exc)
    return out


def _load_state(path: str) -> dict:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("handled"), dict):
            return raw
    except (OSError, ValueError):
        pass
    return {"handled": {}}


def _save_state(path: str, state: dict, now: datetime) -> None:
    cutoff = now - timedelta(days=STATE_RETENTION_DAYS)
    kept = {}
    for cid, ts in state["handled"].items():
        try:
            if datetime.fromisoformat(ts) >= cutoff:
                kept[cid] = ts
        except (TypeError, ValueError):
            continue
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"handled": kept}, ensure_ascii=False, indent=0), encoding="utf-8")
