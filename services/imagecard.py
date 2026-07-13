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
