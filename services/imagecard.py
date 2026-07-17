"""Render a Quote Card unit into a 1080×1350 branded PNG for Instagram.

Pillow-only — no network, no external service, runs in CI. The CJK font is
resolved from IG_FONT_PATH, else a local asset, else a system Noto/WenQuanYi
font, so it works both locally and on the runner (which apt-installs
fonts-noto-cjk). P1 of docs/instagram-plan.md.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:  # pragma: no cover - surfaced at runtime
    Image = None

W, H = 1080, 1350          # 4:5 portrait — max feed real estate
MARGIN = 96
BG = (13, 17, 23)          # near-black navy
FG = (237, 240, 244)       # near-white
ACCENT = (86, 211, 159)    # brand green
SUB = (139, 150, 163)      # muted label grey
HANDLE = "@90s.pm.investing"

_ASSET_FONT = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "NotoSansTC-Bold.otf"
_FONT_CANDIDATES = (
    os.getenv("IG_FONT_PATH", ""),
    str(_ASSET_FONT),
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKtc-Bold.otf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
)


def card_quote(post_body: str) -> str:
    """The card text = the Post Body minus its CTA line (the {CTA_URL}
    placeholder / a 👉 sell line / a bare link line)."""
    kept = []
    for ln in (post_body or "").splitlines():
        s = ln.strip()
        if "{CTA_URL}" in s or "👉" in s or s.startswith("http"):
            continue
        kept.append(ln)
    return "\n".join(kept).strip()


def _font_path() -> str:
    for p in _FONT_CANDIDATES:
        if p and Path(p).exists():
            return p
    raise RuntimeError("No CJK font found; set IG_FONT_PATH or install fonts-noto-cjk.")


def _wrap_cjk(text: str, font, draw, max_w: float) -> list[str]:
    """Wrap by character — CJK has no spaces. Explicit newlines are kept."""
    lines: list[str] = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            if draw.textlength(cur + ch, font=font) <= max_w or not cur:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        lines.append(cur)
    return lines


# ── carousel (multi-slide) ────────────────────────────────────────────────────
# Layout follows the approved #102 draft: cover = big hook + curiosity sub +
# swipe cue; content slides = numbered kicker + headline + short body; last
# slide = Save/Follow CTA. A bottom progress bar fills slide by slide (the
# visual-continuity element that lifts completion rate).

TRACK = (38, 44, 52)
BODY_FG = (200, 206, 214)


def load_carousel_spec(path) -> dict:
    """Read a carousels/<issue>.json slide script. Raises with a clear message
    on a malformed file so the workflow log says what to fix."""
    import json
    raw = Path(path).read_text(encoding="utf-8")
    spec = json.loads(raw)
    if not isinstance(spec, dict) or not isinstance(spec.get("slides"), list):
        raise ValueError(f"{path}: expected an object with a 'slides' array.")
    if not (2 <= len(spec["slides"]) <= 10):
        raise ValueError(f"{path}: IG carousels take 2-10 slides, got {len(spec['slides'])}.")
    return spec


def _text_block(d, text, font, x, y, max_w, fill, line_h_mult=1.5):
    lines: list[str] = []
    for para in (text or "").split("\n"):
        lines += _wrap_cjk(para, font, d, max_w)
    line_h = font.size * line_h_mult
    for ln in lines:
        d.text((x, y), ln, font=font, fill=fill)
        y += line_h
    return y


def render_carousel(spec: dict, out_dir: str, handle: str = HANDLE,
                    font_path: Optional[str] = None) -> list[str]:
    """Render every slide of a carousel spec into out_dir/<nn>.png.
    Returns the paths in slide order."""
    if Image is None:
        raise RuntimeError("Pillow is not installed. `pip install -r requirements.txt`")
    fp = font_path or _font_path()

    def F(size):
        return ImageFont.truetype(fp, size)

    slides = spec["slides"]
    n = len(slides)
    out_paths: list[str] = []
    Path(out_dir).mkdir(parents=True, exist_ok=True)

    for i, s in enumerate(slides):
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        kind = s.get("kind", "content")

        if kind == "cover":
            d.rectangle([MARGIN, 96, MARGIN + 84, 104], fill=ACCENT)
            d.text((MARGIN, 128), s.get("kicker", ""), font=F(34), fill=SUB)
            y = _text_block(d, s.get("head", ""), F(116), MARGIN, 380, W - 2 * MARGIN, FG, 1.35)
            _text_block(d, s.get("sub", ""), F(46), MARGIN, y + 40, W - 2 * MARGIN, SUB, 1.55)
            cue, f = "往右滑", F(40)
            cw = d.textlength(cue, font=f)
            d.text((W - MARGIN - cw - 70, H - 232), cue, font=f, fill=SUB)
            d.text((W - MARGIN - 56, H - 244), "→", font=F(56), fill=ACCENT)
        elif kind == "cta":
            if s.get("bookmark", True):
                # Drawn bookmark glyph (fonts here have no colour emoji) — only
                # when the slide actually asks for a Save.
                bx, by, bw, bh = MARGIN, 150, 64, 88
                d.polygon([(bx, by), (bx + bw, by), (bx + bw, by + bh),
                           (bx + bw / 2, by + bh - 26), (bx, by + bh)], fill=ACCENT)
            else:
                d.rectangle([MARGIN, 96, MARGIN + 84, 104], fill=ACCENT)
            y = _text_block(d, s.get("head", ""), F(104), MARGIN, 340, W - 2 * MARGIN, FG, 1.35)
            y = _text_block(d, s.get("body", ""), F(46), MARGIN, y + 36, W - 2 * MARGIN, SUB, 1.55)
            d.text((MARGIN, y + 70), s.get("follow", ""), font=F(52), fill=ACCENT)
            d.text((MARGIN, y + 170), s.get("link", ""), font=F(44), fill=SUB)
        else:
            kicker = s.get("kicker", "")
            num, _, label = kicker.partition(" · ")
            f_k = F(40)
            d.text((MARGIN, 120), num, font=f_k, fill=ACCENT)
            if label:
                d.text((MARGIN + d.textlength(num, font=f_k) + 28, 120),
                       "· " + label, font=f_k, fill=SUB)
            y = _text_block(d, s.get("head", ""), F(88), MARGIN, 330, W - 2 * MARGIN, FG, 1.4)
            _text_block(d, s.get("body", ""), F(48), MARGIN, y + 44, W - 2 * MARGIN, BODY_FG, 1.62)

        if kind != "cover":
            f = F(30)
            hw = d.textlength(handle, font=f)
            d.text((W - MARGIN - hw, 128), handle, font=f,
                   fill=TRACK if kind == "content" else SUB)

        # Progress bar + page number; arrow on every slide but the last.
        y_bar = H - 120
        d.rectangle([MARGIN, y_bar, W - MARGIN, y_bar + 8], fill=TRACK)
        d.rectangle([MARGIN, y_bar, MARGIN + (W - 2 * MARGIN) * (i + 1) / n, y_bar + 8], fill=ACCENT)
        page, f_p = f"{i + 1}/{n}", F(34)
        d.text((W - MARGIN - d.textlength(page, font=f_p), y_bar + 28), page, font=f_p, fill=SUB)
        if i < n - 1:
            d.text((MARGIN, y_bar + 24), "→", font=F(44), fill=ACCENT)

        out_path = str(Path(out_dir) / f"{i + 1:02d}.png")
        img.save(out_path, "PNG")
        out_paths.append(out_path)
    return out_paths


def render_card(quote: str, issue, out_path: str, handle: str = HANDLE,
                font_path: Optional[str] = None) -> str:
    """Render `quote` onto a branded card and save a PNG at `out_path`."""
    if Image is None:
        raise RuntimeError("Pillow is not installed. `pip install -r requirements.txt`")
    quote = (quote or "").strip()
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    fp = font_path or _font_path()

    box_w = W - 2 * MARGIN
    body_top, body_bottom = 340, H - 300
    # Auto-fit: shrink the type until the wrapped quote fits the body box.
    size = 92
    while size >= 40:
        font = ImageFont.truetype(fp, size)
        lines = _wrap_cjk(quote, font, d, box_w)
        line_h = size * 1.5
        total = len(lines) * line_h
        if total <= (body_bottom - body_top):
            break
        size -= 4

    # Opening quotation glyph.
    quote_font = ImageFont.truetype(fp, 150)
    d.text((MARGIN - 6, body_top - 190), "「", font=quote_font, fill=ACCENT)

    # Quote, centred vertically in the body box.
    y = body_top + ((body_bottom - body_top) - total) / 2
    for ln in lines:
        w = d.textlength(ln, font=font)
        d.text(((W - w) / 2, y), ln, font=font, fill=FG)
        y += line_h

    # Header: accent tick + issue label (top-left).
    small = ImageFont.truetype(fp, 34)
    d.rectangle([MARGIN, 96, MARGIN + 84, 104], fill=ACCENT)
    d.text((MARGIN, 128), f"90s.pm 投資 · #{issue}", font=small, fill=SUB)

    # Footer: handle (bottom-right) + full-width hairline above it.
    d.rectangle([MARGIN, H - 176, W - MARGIN, H - 174], fill=(38, 44, 52))
    hw = d.textlength(handle, font=small)
    d.text((W - MARGIN - hw, H - 136), handle, font=small, fill=ACCENT)

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path
