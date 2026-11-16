"""Overlay renderer — Pillow PNG frames + 16:9 cover.

Renders one 1920x1080 PNG per timeline interval, compositing:

  * the knowledge-area background (dark canvas + accent glow),
  * the carry-forward section chip (top-left) — the last ``## section`` heading,
  * a section TitleCard (centered large) while inside a ``titlecard`` segment,
  * a Quote card (rounded rectangle + source) while inside a ``quote`` segment,
  * the active subtitle cue, burned into the bottom 字幕安全区 with a
    legibility pill behind it.

Because this ffmpeg build may lack the ``subtitles``/``drawtext`` filters
(minimal builds have no libass), subtitles and overlays are burned into PNG
frames here and sequenced by the always-available ``overlay``/concat path in
``render.py`` — the pipeline runs regardless of ffmpeg flavor (mvp_plan.md §3).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .model import (
    SAFE_BOTTOM_MARGIN_PX,
    SAFE_SIDE_MARGIN_PX,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
    ZhiScript,
)

# --- palette (B站 知识区: 深色底 + 蓝紫 accent) ---
BG = (14, 14, 18)  # #0E0E12
BG_PANEL = (24, 24, 30)
ACCENT = (0, 113, 227)  # #0071E3
ACCENT_SOFT = (94, 92, 230)  # #5E5CE6
TEXT_MAIN = (245, 245, 247)
TEXT_DIM = (161, 161, 168)
SUBTITLE_TEXT = (255, 255, 255)
SUBTITLE_PILL = (0, 0, 0, 170)

# CJK + Latin font candidates (first existing wins; last-resort = PIL default).
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/wqy-microhei/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}
_DEFAULT_FONT: ImageFont.FreeTypeFont | None = None


def _resolve_font(size: int) -> ImageFont.FreeTypeFont:
    global _DEFAULT_FONT
    if _DEFAULT_FONT is None:
        for cand in _FONT_CANDIDATES:
            if Path(cand).exists():
                _DEFAULT_FONT = cand  # type: ignore[assignment]
                break
    if _DEFAULT_FONT is None:
        _DEFAULT_FONT = True  # type: ignore[assignment]
        return ImageFont.load_default()
    key = ("main", size)
    if key not in _font_cache:
        try:
            _font_cache[key] = ImageFont.truetype(_DEFAULT_FONT, size)  # type: ignore[arg-type]
        except Exception:
            return ImageFont.load_default()
    return _font_cache[key]


def _text_size(draw: ImageDraw.ImageDraw, text: str, font) -> tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _fit_wrap(text: str, font, max_width: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """Wrap text to fit max_width, breaking on spaces (ASCII) or anywhere
    (CJK, where words are characters). A word wider than the whole line is
    hard-broken; a line break never cuts a word that would fit on its own."""
    out: list[str] = []
    for raw_line in text.split("\n"):
        if not raw_line:
            out.append("")
            continue
        cur = ""
        for ch in raw_line:
            while cur and _text_size(draw, cur + ch, font)[0] > max_width:
                cut = cur.rfind(" ")
                if cut > 0:
                    out.append(cur[:cut])
                    cur = cur[cut + 1:]
                else:
                    out.append(cur)
                    cur = ""
            cur += ch
        out.append(cur)
    return out


@dataclass
class Scene:
    png_path: str
    start_ms: int
    end_ms: int

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)


def _segment_at(script: ZhiScript, ms: int):
    for seg in script.segments:
        if seg.start_ms <= ms < seg.end_ms:
            return seg
    # fall to the last segment that has ended (carry context)
    last = None
    for seg in script.segments:
        if seg.end_ms <= ms:
            last = seg
    return last


def _section_title_before(script: ZhiScript, ms: int) -> str:
    title = ""
    for seg in script.segments:
        if seg.end_ms > ms:
            break
        if seg.kind == "titlecard":
            title = seg.text
    return title


def _draw_background(img: Image.Image) -> Image.Image:
    draw = ImageDraw.Draw(img, "RGBA")
    draw.rectangle([0, 0, VIDEO_WIDTH, VIDEO_HEIGHT], fill=BG)
    # accent radial-ish glow at top center (cheap: blurred ellipse)
    glow = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse(
        [VIDEO_WIDTH // 2 - 520, -360, VIDEO_WIDTH // 2 + 520, 240],
        fill=(*ACCENT, 60),
    )
    img = Image.alpha_composite(img, glow.filter(ImageFilter.GaussianBlur(120)))
    return img


def _draw_section_chip(img: Image.Image, title: str) -> None:
    if not title:
        return
    draw = ImageDraw.Draw(img, "RGBA")
    font = _resolve_font(26)
    chip_pad_x, chip_pad_y = 24, 14
    tw, th = _text_size(draw, title, font)
    x0, y0 = 48, 48
    x1, y1 = x0 + tw + chip_pad_x * 2, y0 + th + chip_pad_y * 2
    draw.rounded_rectangle([x0, y0, x1, y1], radius=12, fill=(*BG_PANEL, 230), outline=ACCENT, width=2)
    draw.text((x0 + chip_pad_x, y0 + chip_pad_y - 2), title, font=font, fill=TEXT_MAIN)


def _draw_titlecard(img: Image.Image, seg) -> None:
    draw = ImageDraw.Draw(img, "RGBA")
    font = _resolve_font(78)
    wrapped = _fit_wrap(seg.text, font, VIDEO_WIDTH - 320, draw)
    # stack lines centered
    line_h = _text_size(draw, "Ay中", font)[1] + 22
    total_h = line_h * len(wrapped)
    y = (VIDEO_HEIGHT - total_h) // 2
    for line in wrapped:
        tw = _text_size(draw, line, font)[0]
        draw.text(((VIDEO_WIDTH - tw) // 2, y), line, font=font, fill=TEXT_MAIN)
        y += line_h
    # accent rule
    ry = y + 18
    draw.rounded_rectangle(
        [VIDEO_WIDTH // 2 - 80, ry, VIDEO_WIDTH // 2 + 80, ry + 6],
        radius=3,
        fill=ACCENT,
    )


# Quote card font ladder: the largest size whose wrapped card fits the canvas
# height wins; 24 is the floor for very long quotes.
_QUOTE_FONT_SIZES = (40, 36, 32, 28, 24)
# 64px breathing margin top/bottom around the quote card.
_QUOTE_CARD_MAX_H = VIDEO_HEIGHT - 128
# Pathological overflow beyond the 24px floor: the card still starts on-canvas.
_QUOTE_MIN_TOP_PX = 32


def _quote_layout(draw: ImageDraw.ImageDraw, text: str, source: str):
    """Pick the quote font size whose wrapped card fits the canvas height.

    Returns (size, font, source_font, wrapped, line_h, total_h) using the same
    card metrics as before (padding 96 + source line), so short quotes render
    pixel-identical at the original 40px."""
    size, font, source_font, wrapped, line_h, total_h = 24, None, None, [], 0, 0
    for size in _QUOTE_FONT_SIZES:
        font = _resolve_font(size)
        source_font = _resolve_font(max(20, size - 14))
        wrapped = _fit_wrap(text, font, 1280, draw)
        line_h = _text_size(draw, "Ay中", font)[1] + 16
        src_h = (_text_size(draw, source, source_font)[1] + 18) if source else 0
        total_h = line_h * len(wrapped) + src_h + 96
        if total_h <= _QUOTE_CARD_MAX_H:
            break
    return size, font, source_font, wrapped, line_h, total_h


def _draw_quote_card(img: Image.Image, seg) -> None:
    draw = ImageDraw.Draw(img, "RGBA")
    _, font, source_font, wrapped, line_h, total_h = _quote_layout(
        draw, seg.text, seg.source
    )
    x0 = (VIDEO_WIDTH - 1400) // 2
    y0 = (VIDEO_HEIGHT - total_h) // 2
    if y0 < _QUOTE_MIN_TOP_PX:
        y0 = _QUOTE_MIN_TOP_PX
    x1, y1 = x0 + 1400, y0 + total_h
    draw.rounded_rectangle(
        [x0, y0, x1, y1], radius=24, fill=(*BG_PANEL, 235), outline=ACCENT_SOFT, width=2
    )
    # accent left bar
    draw.rounded_rectangle([x0, y0, x0 + 8, y1], radius=4, fill=ACCENT_SOFT)
    cy = y0 + 48
    for line in wrapped:
        draw.text((x0 + 56, cy), line, font=font, fill=TEXT_MAIN)
        cy += line_h
    if seg.source:
        draw.text((x0 + 56, cy + 4), f"— {seg.source}", font=source_font, fill=TEXT_DIM)


def _draw_subtitle(img: Image.Image, cue) -> None:
    if cue is None:
        return
    draw = ImageDraw.Draw(img, "RGBA")
    font = _resolve_font(54)
    lines = cue.lines
    line_h = _text_size(draw, "Ay中", font)[1] + 14
    # measure widest line
    widths = [_text_size(draw, ln, font)[0] for ln in lines]
    max_w = max(widths) if widths else 0
    block_h = line_h * len(lines)
    # bottom safe area box
    box_w = max_w + 96
    box_h = block_h + 48
    x0 = (VIDEO_WIDTH - box_w) // 2
    y1 = VIDEO_HEIGHT - SAFE_BOTTOM_MARGIN_PX
    y0 = y1 - box_h
    draw.rounded_rectangle(
        [x0, y0, x0 + box_w, y1], radius=18, fill=SUBTITLE_PILL
    )
    cy = y0 + 24
    for ln, lw in zip(lines, widths):
        draw.text(((VIDEO_WIDTH - lw) // 2, cy), ln, font=font, fill=SUBTITLE_TEXT)
        cy += line_h


def _render_frame(script: ZhiScript, ms: int, cue, out_path: Path) -> str:
    img = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), BG + (255,))
    img = _draw_background(img)
    seg = _segment_at(script, ms)
    section = _section_title_before(script, ms)
    if seg and seg.kind == "titlecard":
        _draw_titlecard(img, seg)
    else:
        if section:
            _draw_section_chip(img, section)
        if seg and seg.kind == "quote":
            _draw_quote_card(img, seg)
    _draw_subtitle(img, cue)
    out_path = out_path.with_suffix(".png")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(out_path, format="PNG")
    return str(out_path)


def render_cover(script: ZhiScript, out_dir: str | Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), BG + (255,))
    img = _draw_background(img)
    draw = ImageDraw.Draw(img, "RGBA")
    title_font = _resolve_font(92)
    sub_font = _resolve_font(40)
    wrapped = _fit_wrap(script.cover.title, title_font, VIDEO_WIDTH - 320, draw)
    line_h = _text_size(draw, "Ay中", title_font)[1] + 26
    total_h = line_h * len(wrapped)
    y = (VIDEO_HEIGHT - total_h) // 2 - 40
    for line in wrapped:
        tw = _text_size(draw, line, title_font)[0]
        draw.text(((VIDEO_WIDTH - tw) // 2, y), line, font=title_font, fill=TEXT_MAIN)
        y += line_h
    # accent rule
    ry = y + 30
    draw.rounded_rectangle(
        [VIDEO_WIDTH // 2 - 100, ry, VIDEO_WIDTH // 2 + 100, ry + 8],
        radius=4,
        fill=ACCENT,
    )
    if script.cover.subtitle:
        sw = _text_size(draw, script.cover.subtitle, sub_font)[0]
        draw.text(
            ((VIDEO_WIDTH - sw) // 2, ry + 36),
            script.cover.subtitle,
            font=sub_font,
            fill=TEXT_DIM,
        )
    cover = out_dir / "cover.png"
    img.convert("RGB").save(cover, format="PNG")
    return cover


def build_scenes(script: ZhiScript, out_dir: str | Path) -> list[Scene]:
    """Tile [0, total_ms] into intervals; render one PNG per interval, with
    the active subtitle cue burned in (None during 弹幕-rhythm gaps)."""
    out_dir = Path(out_dir)
    scenes_dir = out_dir / "scenes"
    scenes_dir.mkdir(parents=True, exist_ok=True)
    cues = script.subtitle_cues
    total = script.total_ms
    if total <= 0:
        return []

    events = sorted({0, total, *[c.start_ms for c in cues], *[c.end_ms for c in cues]})
    scenes: list[Scene] = []
    idx = 0
    for i in range(len(events) - 1):
        s, e = events[i], events[i + 1]
        if e <= s:
            continue
        mid = (s + e) // 2
        active = next((c for c in cues if c.start_ms <= mid < c.end_ms), None)
        png = _render_frame(script, mid, active, scenes_dir / f"scene_{idx:05d}.png")
        scenes.append(Scene(png_path=png, start_ms=s, end_ms=e))
        idx += 1
    return scenes


def attach_overlay_plan(script: ZhiScript) -> ZhiScript:
    """Derive 引用/section overlay cards from segments (for the manifest +
    SRT-interop consumers). Frame rendering does not depend on this list, but
    it records which cards appear when."""
    from .model import OverlayCard

    cards: list[OverlayCard] = []
    for seg in script.segments:
        if seg.kind == "titlecard":
            cards.append(
                OverlayCard(
                    kind="section", title=seg.text, start_ms=seg.start_ms, end_ms=seg.end_ms
                )
            )
        elif seg.kind == "quote":
            cards.append(
                OverlayCard(
                    kind="quote",
                    title=seg.source or "引用",
                    body=seg.text,
                    start_ms=seg.start_ms,
                    end_ms=seg.end_ms,
                )
            )
    return script.model_copy(update={"overlay_cards": cards})
