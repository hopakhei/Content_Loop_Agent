#!/usr/bin/env python3
"""Fetch CC0 stock photos for carousel cover slides and crop them to 4:5.

Runs on a GitHub Actions runner, not in the agent sandbox — the sandbox's
network policy blocks every image host, while the runner has open internet.
Images land in backgrounds/<slug>-cover.jpg and are committed, so rendering
itself never touches the network.

Licensing: the search is pinned to `license=cc0,pdm` (CC0 and Public Domain
Mark). Those carry no attribution obligation, which is what a brand account
posting daily needs — a CC-BY photo would require crediting the photographer
in every caption. backgrounds/sources.json records where each file came from
anyway, so provenance is auditable.

Usage:
    python scripts/fetch_backgrounds.py               # only missing slugs
    python scripts/fetch_backgrounds.py --force       # refetch everything
    python scripts/fetch_backgrounds.py porter        # just these slugs
"""
from __future__ import annotations

import argparse
import os
import json
import sys
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

BASE = Path(__file__).resolve().parent.parent
QUERIES = BASE / "assets" / "background_queries.json"
OUT_DIR = BASE / "backgrounds"
SOURCES = OUT_DIR / "sources.json"

API = "https://api.openverse.org/v1/images/"
UA = "90spm-investing-carousel/1.0 (+https://github.com/hopakhei/Content_Loop_Agent)"
W, H = 1080, 1350          # 4:5, matching the renderer canvas
MIN_W, MIN_H = 1080, 1080  # reject anything too small to crop cleanly

# Openverse hands back watermarked *preview* files for these providers even
# when the underlying work is CC0 — a rawpixel result arrived tiled with the
# word "rawpixel" across the frame. Unusable as a background, so skip them.
WATERMARKED_SOURCES = {"rawpixel"}

# Optional higher-quality providers. Both licences allow commercial use with
# no mandatory attribution, and their libraries dwarf the CC0-only pool, which
# in practice returns nothing for most of these framework subjects. Set either
# key as a repo secret to switch over; without one the script stays on
# Openverse/CC0.
PEXELS_KEY = os.getenv("PEXELS_API_KEY", "").strip()
UNSPLASH_KEY = os.getenv("UNSPLASH_ACCESS_KEY", "").strip()


def _search_pexels(query: str, want: int) -> list[dict]:
    r = requests.get(
        "https://api.pexels.com/v1/search",
        params={"query": query, "per_page": want, "orientation": "portrait"},
        headers={"Authorization": PEXELS_KEY, "User-Agent": UA}, timeout=45,
    )
    r.raise_for_status()
    return [{"url": p["src"]["original"], "title": p.get("alt"),
             "creator": p.get("photographer"), "license": "pexels",
             "source": "pexels", "foreign_landing_url": p.get("url")}
            for p in r.json().get("photos", [])]


def _search_unsplash(query: str, want: int) -> list[dict]:
    r = requests.get(
        "https://api.unsplash.com/search/photos",
        params={"query": query, "per_page": want, "orientation": "portrait"},
        headers={"Authorization": f"Client-ID {UNSPLASH_KEY}", "User-Agent": UA},
        timeout=45,
    )
    r.raise_for_status()
    return [{"url": p["urls"]["raw"] + "&w=1600&fm=jpg", "title": p.get("alt_description"),
             "creator": (p.get("user") or {}).get("name"), "license": "unsplash",
             "source": "unsplash", "foreign_landing_url": (p.get("links") or {}).get("html")}
            for p in r.json().get("results", [])]


def _search_openverse(query: str, want: int) -> list[dict]:
    r = requests.get(
        API,
        params={"q": query, "license": "cc0,pdm", "size": "large",
                "page_size": want, "mature": "false"},
        headers={"User-Agent": UA}, timeout=45,
    )
    r.raise_for_status()
    return [c for c in r.json().get("results", [])
            if (c.get("source") or "").lower() not in WATERMARKED_SOURCES]


def search(query: str, want: int = 8) -> list[dict]:
    """Prefer a keyed provider when one is configured; fall back to CC0."""
    if PEXELS_KEY:
        return _search_pexels(query, want)
    if UNSPLASH_KEY:
        return _search_unsplash(query, want)
    return _search_openverse(query, want)


def cover_crop(im: Image.Image) -> Image.Image:
    """Scale so both axes are covered, then centre-crop to W×H."""
    im = im.convert("RGB")
    scale = max(W / im.width, H / im.height)
    im = im.resize((max(W, int(im.width * scale)), max(H, int(im.height * scale))),
                   Image.LANCZOS)
    left, top = (im.width - W) // 2, (im.height - H) // 2
    return im.crop((left, top, left + W, top + H))


def fetch_one(slug: str, query: str) -> dict | None:
    """Try candidates in rank order; the first one that downloads and is big
    enough wins. Openverse results occasionally 404 or point at a dead host,
    so a single candidate is not enough to be reliable."""
    try:
        candidates = search(query)
    except Exception as exc:
        print(f"  ! search failed for {slug}: {exc}")
        return None
    if not candidates:
        print(f"  ! no CC0 results for {slug} (query: {query!r})")
        return None

    for c in candidates:
        url = c.get("url")
        if not url:
            continue
        try:
            resp = requests.get(url, headers={"User-Agent": UA}, timeout=60)
            resp.raise_for_status()
            im = Image.open(BytesIO(resp.content))
            if im.width < MIN_W or im.height < MIN_H:
                print(f"    skip {im.width}×{im.height} (too small)")
                continue
            out = OUT_DIR / f"{slug}-cover.jpg"
            cover_crop(im).save(out, "JPEG", quality=88, optimize=True)
            print(f"  ✓ {slug}: {im.width}×{im.height} → {out.name}")
            return {"slug": slug, "query": query, "file": out.name,
                    "title": c.get("title"), "creator": c.get("creator"),
                    "license": c.get("license"), "source": c.get("source"),
                    "landing_page": c.get("foreign_landing_url"), "url": url}
        except Exception as exc:
            print(f"    skip candidate: {exc}")
    print(f"  ! every candidate failed for {slug}")
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("slugs", nargs="*", help="limit to these slugs")
    ap.add_argument("--force", action="store_true", help="refetch existing files")
    args = ap.parse_args()

    queries = {k: v for k, v in json.loads(QUERIES.read_text("utf-8")).items()
               if not k.startswith("_")}
    if args.slugs:
        missing = [s for s in args.slugs if s not in queries]
        if missing:
            print(f"unknown slug(s): {', '.join(missing)}", file=sys.stderr)
            return 2
        queries = {s: queries[s] for s in args.slugs}

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    records = json.loads(SOURCES.read_text("utf-8")) if SOURCES.exists() else {}

    got = 0
    for slug, query in queries.items():
        if not args.force and (OUT_DIR / f"{slug}-cover.jpg").exists():
            print(f"  · {slug}: already present, skipping")
            continue
        print(f"→ {slug}: {query!r}")
        rec = fetch_one(slug, query)
        if rec:
            records[slug] = rec
            got += 1

    SOURCES.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", "utf-8")
    print(f"\n{got} image(s) fetched; {len(records)} recorded in {SOURCES.name}")
    # No exit-code failure on partial results: some slugs finding nothing is a
    # normal outcome for a CC0-only search, and the renderer falls back to the
    # line-art motif for any slug without a file.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
