"""ZhiScript manifest — the core primitive.

A parsed markdown script turned into a structured, B站-format-constrained video
plan (see mvp_plan.md §2). The moat-carrying pieces are:

  * ``subtitle_cues`` — 字幕安全区-constrained cues (≤14 chars/line, ≤2 lines,
    bottom safe area) derived directly from TTS word-boundary timestamps.
  * ``segments`` — 知识区 narrative structure (开场hook → 论证 → 总结), with
    markdown headings mapped to TitleCard and ``>`` quote blocks to Quote cards.
"""

from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel, Field

# --- safe-area constants (B站 知识区 16:9 字幕安全区) ---
SAFE_MAX_CHARS_PER_LINE = 14
SAFE_MAX_LINES = 2
SAFE_BOTTOM_MARGIN_PX = 96  # gap from the bottom edge to the subtitle baseline box
SAFE_SIDE_MARGIN_PX = 160

# canvas
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30


class CoverSpec(BaseModel):
    """16:9 cover PNG spec: title + accent."""

    title: str
    subtitle: str = ""
    accent: str = "#0071E3"
    bg: str = "#0E0E12"


class WordBoundary(BaseModel):
    """One word with timing relative to its segment's audio start (ms)."""

    text: str
    offset_ms: int
    duration_ms: int


class Segment(BaseModel):
    """A narration/quote/title segment. Timings are absolute (ms) in the
    full video timeline; filled by ``tts.synthesize``."""

    kind: Literal["narration", "quote", "titlecard"]
    text: str
    source: str = ""  # only for quote: who said it / where cited
    start_ms: int = 0
    end_ms: int = 0
    audio_path: str | None = None
    boundaries: list[WordBoundary] = Field(default_factory=list)

    @property
    def duration_ms(self) -> int:
        return max(0, self.end_ms - self.start_ms)


class SubtitleCue(BaseModel):
    """One subtitle cue, already wrapped to 字幕安全区 rules."""

    index: int
    start_ms: int
    end_ms: int
    lines: list[str]  # ≤ SAFE_MAX_LINES, each ≤ SAFE_MAX_CHARS_PER_LINE

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


class OverlayCard(BaseModel):
    """A 引用/section overlay card placed on the canvas for a time range."""

    kind: Literal["quote", "section"]
    title: str
    body: str = ""
    start_ms: int
    end_ms: int


class RenderSpec(BaseModel):
    width: int = VIDEO_WIDTH
    height: int = VIDEO_HEIGHT
    fps: int = VIDEO_FPS
    crf: int = 23
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    pix_fmt: str = "yuv420p"


class ZhiScript(BaseModel):
    """The full video plan. parse.py builds the static parts; tts.py fills
    timings + audio; subtitle.py + overlay.py fill the cue/card plans."""

    title: str
    cover: CoverSpec
    segments: list[Segment]
    subtitle_cues: list[SubtitleCue] = Field(default_factory=list)
    overlay_cards: list[OverlayCard] = Field(default_factory=list)
    render: RenderSpec = Field(default_factory=RenderSpec)

    @property
    def total_ms(self) -> int:
        ends = [s.end_ms for s in self.segments if s.end_ms > 0]
        return max(ends) if ends else 0


SegmentUnion = Union[Segment]  # single concrete model; kind discriminator in-field
