"""Text wrapping in overlay cards — break at spaces, hard-break only when needed.

v0.4.0 fix: _fit_wrap's docstring promised to break "on spaces (ASCII)", but the
loop flushed the whole buffer on overflow, so a title card rendered
"Retrieval-Augmented Gene" / "ration pipelines". The same wrapper draws title
cards and the cover title.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from zhicast.overlay import _fit_wrap, _resolve_font


def _draw() -> ImageDraw.ImageDraw:
    return ImageDraw.Draw(Image.new("RGBA", (1920, 1080), (0, 0, 0, 255)), "RGBA")


def _width(draw: ImageDraw.ImageDraw, text: str, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


ASCII_TEXT = (
    "Evaluation of Retrieval-Augmented Generation pipelines for knowledge videos"
)


def test_ascii_wrap_breaks_at_spaces():
    draw, font = _draw(), _resolve_font(40)
    # Narrower than the sentence, wider than its longest word: every break must
    # land on a space, so re-joining the lines reproduces the input.
    max_width = int(_width(draw, ASCII_TEXT, font) * 0.55)
    longest = max(ASCII_TEXT.split(" "), key=lambda w: _width(draw, w, font))
    assert _width(draw, longest, font) <= max_width  # no hard break is needed
    lines = _fit_wrap(ASCII_TEXT, font, max_width, draw)
    assert len(lines) > 1
    assert " ".join(lines) == ASCII_TEXT
    for line in lines:
        assert _width(draw, line, font) <= max_width


def test_cjk_wrap_still_char_breaks_without_loss():
    draw, font = _draw(), _resolve_font(40)
    text = "上下文窗口是模型一次能看到的全部内容它决定了模型的工作记忆上限"
    max_width = int(_width(draw, text, font) * 0.4)
    lines = _fit_wrap(text, font, max_width, draw)
    assert len(lines) > 1
    assert "".join(lines) == text
    for line in lines:
        assert _width(draw, line, font) <= max_width


def test_wrap_honors_existing_multiline_input():
    draw, font = _draw(), _resolve_font(40)
    text = "第一段\n第二段"
    lines = _fit_wrap(text, font, _width(draw, text, font), draw)
    assert lines == ["第一段", "第二段"]
