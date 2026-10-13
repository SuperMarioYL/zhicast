"""Quote card layout — long quotes must stay on-canvas.

v0.3.0 fix: _draw_quote_card used a fixed 40px font, so a long quote computed
y0 = (1080 - total_h) // 2 < 0 and the card (with its text) was drawn partly
off the top of the canvas. The card now auto-shrinks through a font ladder
and clamps to the canvas for pathological inputs.

Font-size assertions only run when a real (truetype) font is resolvable:
CI runners have no CJK font, Pillow falls back to its size-independent
bitmap default, and the ladder is a no-op there. The on-canvas invariant
is pinned for every environment.
"""

from __future__ import annotations

import zhicast.overlay as overlay
from PIL import Image, ImageDraw

from zhicast.model import Segment, ZhiScript, CoverSpec
from zhicast.overlay import (
    _QUOTE_CARD_MAX_H,
    _QUOTE_MIN_TOP_PX,
    _quote_layout,
    render_cover,
)

SHORT_QUOTE = "注意力机制的本质是一场受预算约束的回忆。"
# ~1420 CJK chars: at the old fixed 40px this wrapped to 22 lines / y0 = -175.
LONG_QUOTE = "这是一段非常长的引用内容用来测试引用卡片在文本超长时是否会溢出画布。" * 20


def _draw() -> ImageDraw.ImageDraw:
    img = Image.new("RGBA", (1920, 1080), (0, 0, 0, 255))
    return ImageDraw.Draw(img, "RGBA")


def _card_geometry(text: str, source: str = "测试来源") -> tuple[int, int, int]:
    """(font_size, y0_after_clamp, total_h) exactly as _draw_quote_card lays out."""
    size, _, _, wrapped, line_h, total_h = _quote_layout(_draw(), text, source)
    y0 = (1080 - total_h) // 2
    if y0 < _QUOTE_MIN_TOP_PX:
        y0 = _QUOTE_MIN_TOP_PX
    return size, y0, total_h


def _real_font() -> bool:
    # _resolve_font caches its choice: a path string = truetype, True = bitmap fallback
    return isinstance(overlay._DEFAULT_FONT, str)


def test_short_quote_keeps_original_layout():
    size, y0, total_h = _card_geometry(SHORT_QUOTE)
    assert size == 40  # unchanged look for the common case
    assert y0 == (1080 - total_h) // 2  # centered, unclamped


def test_long_quote_stays_on_canvas():
    size, y0, total_h = _card_geometry(LONG_QUOTE)
    assert y0 >= _QUOTE_MIN_TOP_PX  # never drawn off the top edge
    assert y0 + total_h <= 1080  # bottom stays on-canvas
    if _real_font():
        assert size < 40  # font ladder engaged
        assert total_h <= _QUOTE_CARD_MAX_H


def test_pathological_quote_still_starts_on_canvas():
    huge = LONG_QUOTE * 4
    size, y0, total_h = _card_geometry(huge)
    assert y0 >= _QUOTE_MIN_TOP_PX  # pinned regardless of font availability
    if _real_font():
        assert size == 24  # at the font floor
        assert y0 == _QUOTE_MIN_TOP_PX  # clamped instead of negative


def test_quote_frame_renders_without_crash(tmp_path):
    seg = Segment(kind="quote", text=LONG_QUOTE, source="测试来源")
    s = ZhiScript(
        title="t",
        cover=CoverSpec(title="t"),
        segments=[Segment(kind="narration", text="旁白", start_ms=0, end_ms=1000), seg],
    )
    cover = render_cover(s, tmp_path)
    assert cover.exists()
