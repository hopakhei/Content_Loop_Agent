"""Render a Quote Card unit into a 1080×1350 branded PNG for Instagram.

Pillow-only — no network, no external service, runs in CI. The CJK font is
resolved from IG_FONT_PATH, else a local asset, else a system Noto/WenQuanYi
font, so it works both locally and on the runner (which apt-installs
fonts-noto-cjk). P1 of docs/instagram-plan.md.
"""
from __future__ import annotations

import os
import re
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


_LATIN_RUN = re.compile(r"[A-Za-z0-9$%&@#'./\-]+|.")
_NO_LINE_START = "。，、．：；！？…—」』）%％"   # closers hang on the previous line
_NO_LINE_END = "「『（"                          # openers move to the next line


def _wrap_cjk(text: str, font, draw, max_w: float) -> list[str]:
    """Wrap by character — CJK has no spaces — but keep latin/number runs
    ("Berkshire", "P/E", "$0", "30-50%") unbroken and apply kinsoku rules.
    Explicit newlines are kept."""
    lines: list[str] = []
    for para in text.split("\n"):
        cur = ""
        for tok in _LATIN_RUN.findall(para):
            if not cur and draw.textlength(tok, font=font) > max_w:
                for ch in tok:
                    if cur and draw.textlength(cur + ch, font=font) > max_w:
                        lines.append(cur)
                        cur = ""
                    cur += ch
                continue
            if (draw.textlength(cur + tok, font=font) <= max_w or not cur
                    or tok in _NO_LINE_START):
                cur += tok
            else:
                line = cur.rstrip(" ")
                carry = ""
                while line and line[-1] in _NO_LINE_END:
                    carry = line[-1] + carry
                    line = line[:-1]
                lines.append(line)
                cur = carry + ("" if tok == " " else tok)
        lines.append(cur.rstrip(" "))
    return lines


# ── carousel (multi-slide) ────────────────────────────────────────────────────
# Layout follows the approved #102 draft: cover = big hook + curiosity sub +
# swipe cue; content slides = numbered kicker + headline + short body; last
# slide = Save/Follow CTA. A bottom progress bar fills slide by slide (the
# visual-continuity element that lifts completion rate).

TRACK = (38, 44, 52)
BODY_FG = (200, 206, 214)
# Halo painted under type that sits on a photo. Near-black rather than
# pure black so it reads as depth instead of an outline.
SHADOW = (6, 9, 13)

# ── slide motifs ─────────────────────────────────────────────────────────────
# A faint line drawing of the framework itself, painted behind the text so each
# slide carries a visual echo of what it explains (a 2×2 for a matrix, a decay
# curve for the experience curve, five inward arrows for the five forces…).
# Drawn with Pillow primitives — no image assets, no network, deterministic in
# CI. MOTIF sits ~15 levels above BG: legible as texture, never competing with
# body copy. Opt in per slide with "motif", or per carousel with a top-level
# "motif" default.
MOTIF = (28, 36, 46)
MOTIF_KEY = (34, 52, 51)      # accent-tinted, for the one line worth noticing


def _photo_bg(img, path, dim: float = 0.62, blur: int = 5):
    """Composite a real photograph behind the slide.

    Cover-fits the image to the canvas, blurs it, then lays a dark scrim over
    it at `dim` opacity. Both steps are the point: dense Traditional Chinese
    body copy over an unmodified photo is unreadable, so the picture has to
    read as atmosphere rather than subject. The type is drawn with a shadow
    halo over a photo, which is what carries legibility — that is why the
    default scrim can sit at 0.62 and leave the picture clearly visible
    instead of the 0.80 needed when the glyphs are unprotected.

    Photos are committed under backgrounds/ and composited at render time —
    nothing is fetched during a run, so carousel-drip stays offline.
    """
    from PIL import ImageFilter
    src = Image.open(path).convert("RGB")
    # cover-fit: scale so both axes are covered, then centre-crop.
    scale = max(W / src.width, H / src.height)
    src = src.resize((max(1, int(src.width * scale)), max(1, int(src.height * scale))),
                     Image.LANCZOS)
    left, top = (src.width - W) // 2, (src.height - H) // 2
    src = src.crop((left, top, left + W, top + H))
    if blur:
        src = src.filter(ImageFilter.GaussianBlur(blur))
    img.paste(src, (0, 0))
    if dim > 0:
        scrim = Image.new("RGB", (W, H), BG)
        img.paste(Image.blend(src, scrim, min(1.0, dim)), (0, 0))
    return img


def _motif_box(d, cx, cy, r, colour=MOTIF, w=4):
    d.rectangle([cx - r, cy - r, cx + r, cy + r], outline=colour, width=w)


def _draw_motif(d, name: str) -> None:
    """Paint `name` as a large, faint diagram low and right of centre — the
    region body copy rarely reaches, so the texture reads without sitting in
    the middle of a sentence."""
    cx, cy, R = int(W * 0.66), int(H * 0.74), 262

    if name == "grid2x2":                      # BCG matrix, Ansoff
        _motif_box(d, cx, cy, R)
        d.line([cx - R, cy, cx + R, cy], fill=MOTIF, width=4)
        d.line([cx, cy - R, cx, cy + R], fill=MOTIF, width=4)
        d.ellipse([cx + R // 3, cy - R + R // 3, cx + R - R // 6, cy - R // 6],
                  outline=MOTIF_KEY, width=5)
    elif name == "curve-down":                 # experience curve
        d.line([cx - R, cy - R, cx - R, cy + R], fill=MOTIF, width=4)
        d.line([cx - R, cy + R, cx + R, cy + R], fill=MOTIF, width=4)
        pts = [(cx - R + i * (2 * R) / 60,
                cy + R - (2 * R) * (0.92 ** (i * 0.9)) * 0.92)
               for i in range(61)]
        d.line(pts, fill=MOTIF_KEY, width=6, joint="curve")
    elif name == "five-arrows":                # five forces
        _motif_box(d, cx, cy, R // 3, colour=MOTIF_KEY, w=5)
        import math
        for k in range(5):
            a = -math.pi / 2 + k * 2 * math.pi / 5
            x0, y0 = cx + R * math.cos(a), cy + R * math.sin(a)
            x1, y1 = cx + (R // 2.1) * math.cos(a), cy + (R // 2.1) * math.sin(a)
            d.line([x0, y0, x1, y1], fill=MOTIF, width=5)
            d.ellipse([x1 - 9, y1 - 9, x1 + 9, y1 + 9], fill=MOTIF)
    elif name == "scatter-groups":             # strategic group mapping
        d.line([cx - R, cy - R, cx - R, cy + R], fill=MOTIF, width=4)
        d.line([cx - R, cy + R, cx + R, cy + R], fill=MOTIF, width=4)
        clusters = [((-0.45, -0.35), 78, MOTIF_KEY), ((0.30, 0.10), 96, MOTIF),
                    ((0.05, 0.62), 58, MOTIF)]
        for (fx, fy), rr, col in clusters:
            bx, by = cx + fx * R, cy + fy * R
            d.ellipse([bx - rr, by - rr, bx + rr, by + rr], outline=col, width=5)
    elif name == "three-paths":                # Porter generic strategies
        for dy, col in ((-R, MOTIF), (0, MOTIF_KEY), (R, MOTIF)):
            d.line([cx - R, cy, cx + R, cy + dy], fill=col, width=5)
        d.ellipse([cx - R - 12, cy - 12, cx - R + 12, cy + 12], fill=MOTIF_KEY)
    elif name == "chain":                      # value chain
        step = (2 * R) // 5
        for k in range(5):
            x = cx - R + k * step
            col = MOTIF_KEY if k == 3 else MOTIF
            d.line([x, cy - 90, x + step - 18, cy, x, cy + 90], fill=col, width=5)
    elif name == "wave":                       # blue ocean value curve
        for off, col in ((-70, MOTIF), (70, MOTIF_KEY)):
            pts = [(cx - R + k * (2 * R) / 4,
                    cy + off + (90 if k % 2 else -90)) for k in range(5)]
            d.line(pts, fill=col, width=5)
    elif name == "s-curve":                    # disruptive innovation
        import math
        for off, col in ((-120, MOTIF), (140, MOTIF_KEY)):
            pts = [(cx - R + i * (2 * R) / 60,
                    cy + off + R * 0.8 * (1 / (1 + math.exp(-(i - 30) / 7)) - 0.5) * -2)
                   for i in range(61)]
            d.line(pts, fill=col, width=5, joint="curve")
    elif name == "clock":                      # Bowman's strategy clock
        import math
        d.ellipse([cx - R, cy - R, cx + R, cy + R], outline=MOTIF, width=4)
        for k in range(8):
            a = -math.pi / 2 + k * math.pi / 4
            col = MOTIF_KEY if k == 1 else MOTIF
            d.line([cx, cy, cx + R * math.cos(a), cy + R * math.sin(a)], fill=col, width=4)


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


def _text_block(d, text, font, x, y, max_w, fill, line_h_mult=1.5, shadow=False):
    """Lay out wrapped text. `shadow` paints a soft dark copy underneath first
    — over a photograph that is what keeps type crisp, and it is what lets the
    scrim be light enough for the picture to still be worth having. Without it
    the only way to protect legibility is to dim the photo into mush."""
    lines: list[str] = []
    for para in (text or "").split("\n"):
        lines += _wrap_cjk(para, font, d, max_w)
    line_h = font.size * line_h_mult
    # Offsets ring the glyph so the halo reads from every side, not just below.
    off = max(2, round(font.size * 0.035))
    for ln in lines:
        if shadow:
            for dx, dy in ((-off, 0), (off, 0), (0, -off), (0, off),
                           (off, off), (-off, -off)):
                d.text((x + dx, y + dy), ln, font=font, fill=SHADOW)
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

        # Background layers first, so every later stroke sits on top of them.
        # A photo wins over the line-art motif when a slide carries both.
        photo = s.get("image", spec.get("image"))
        if photo:
            p = Path(photo)
            if not p.is_absolute():
                p = Path(__file__).resolve().parent.parent / p
            if p.exists():
                img = _photo_bg(img, p,
                                dim=float(s.get("image_dim", spec.get("image_dim", 0.62))),
                                blur=int(s.get("image_blur", spec.get("image_blur", 5))))
                d = ImageDraw.Draw(img)
            else:
                photo = None      # fall through to the motif
        motif = s.get("motif", spec.get("motif"))
        if motif and not photo:
            _draw_motif(d, motif)

        # Muted grey reads fine on flat near-black, but over a photo — even a
        # dimmed one — the bright patches swallow it. Lift the secondary tones
        # when a picture is behind them.
        sub_fill = (208, 216, 224) if photo else SUB

        if kind == "cover":
            d.rectangle([MARGIN, 96, MARGIN + 84, 104], fill=ACCENT)
            _text_block(d, s.get("kicker", ""), F(34), MARGIN, 128, W - 2*MARGIN, sub_fill, 1.5, shadow=bool(photo))
            y = _text_block(d, s.get("head", ""), F(116), MARGIN, 380, W - 2 * MARGIN, FG, 1.35, shadow=bool(photo))
            _text_block(d, s.get("sub", ""), F(46), MARGIN, y + 40, W - 2 * MARGIN, sub_fill, 1.55, shadow=bool(photo))
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
            y = _text_block(d, s.get("head", ""), F(104), MARGIN, 340, W - 2 * MARGIN, FG, 1.35, shadow=bool(photo))
            y = _text_block(d, s.get("body", ""), F(46), MARGIN, y + 36, W - 2 * MARGIN, BODY_FG if photo else SUB, 1.55, shadow=bool(photo))
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
            y = _text_block(d, s.get("head", ""), F(88), MARGIN, 330, W - 2 * MARGIN, FG, 1.4, shadow=bool(photo))
            _text_block(d, s.get("body", ""), F(48), MARGIN, y + 44, W - 2 * MARGIN, BODY_FG, 1.62, shadow=bool(photo))

        if kind != "cover":
            f = F(30)
            hw = d.textlength(handle, font=f)
            # The near-invisible TRACK tone is deliberate on flat near-black,
            # but over a photo it reads as a smudge rather than a watermark.
            handle_fill = SUB if (photo or kind != "content") else TRACK
            d.text((W - MARGIN - hw, 128), handle, font=f, fill=handle_fill)

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
