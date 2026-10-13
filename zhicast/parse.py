"""Markdown → ZhiScript manifest parser.

Knowledge-area narrative structure (mvp_plan.md §2):

  * the first ``# title`` line → ``ZhiScript.title`` + cover
  * ``## section`` headings → TitleCard segments (章节标题卡)
  * ``> quoted`` blocks → Quote segments (引用标注)
  * plain paragraphs → Narration segments (旁白)

The parser only builds the *static* structure (no timings); ``tts.synthesize``
fills absolute ``start_ms``/``end_ms`` from real audio durations.
"""

from __future__ import annotations

import re
from pathlib import Path

from .model import CoverSpec, Segment, ZhiScript

_HEADING1 = re.compile(r"^#\s+(?P<title>.+?)\s*$")
_HEADING2 = re.compile(r"^##\s+(?P<title>.+?)\s*$")
_QUOTE = re.compile(r"^>\s?(?P<text>.+?)\s*$")
_SOURCE = re.compile(r"\((?P<src>[^)]+)\)\s*$")  # trailing "(来源)" on a quote


def parse_script(markdown: str, *, accent: str = "#0071E3") -> ZhiScript:
    """Parse a markdown knowledge script into a ZhiScript manifest.

    The markdown is split into lines; blank lines separate narration
    paragraphs. Heading-2 lines become TitleCard segments interleaved in
    document order so the timeline reads hook → argument → summary.
    """
    title = "未命名脚本"
    segments: list[Segment] = []

    lines = markdown.splitlines()
    i = 0
    para: list[str] = []
    current_section = ""  # last seen ## heading (carries into following cards)
    in_fence = False  # inside a ``` code block

    def flush_paragraph() -> None:
        nonlocal para
        if para:
            text = " ".join(p.strip() for p in para if p.strip())
            if text:
                segments.append(Segment(kind="narration", text=text))
            para = []

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # Fenced code blocks must never be read as structure: a `# comment`
        # inside ``` would otherwise become the script title, and the fence
        # markers would leak into narration text. Fence lines are dropped;
        # interior lines flow into the current paragraph as plain narration.
        if stripped.startswith("```"):
            flush_paragraph()
            in_fence = not in_fence
            i += 1
            continue

        if in_fence:
            para.append(stripped)
            i += 1
            continue

        if not stripped:
            flush_paragraph()
            i += 1
            continue

        m1 = _HEADING1.match(stripped)
        if m1:
            flush_paragraph()
            title = m1.group("title").strip()
            i += 1
            continue

        m2 = _HEADING2.match(stripped)
        if m2:
            flush_paragraph()
            current_section = m2.group("title").strip()
            segments.append(Segment(kind="titlecard", text=current_section))
            i += 1
            continue

        mq = _QUOTE.match(stripped)
        if mq:
            flush_paragraph()
            quote_text = mq.group("text").strip()
            src_match = _SOURCE.search(quote_text)
            source = ""
            if src_match:
                source = src_match.group("src").strip()
                quote_text = _SOURCE.sub("", quote_text).strip()
            segments.append(
                Segment(
                    kind="quote",
                    text=quote_text,
                    source=source or current_section,
                )
            )
            i += 1
            continue

        para.append(stripped)
        i += 1

    flush_paragraph()

    if not segments:
        # Degenerate input: still emit a single narration segment so the
        # pipeline produces *something* rather than an empty video.
        segments.append(Segment(kind="narration", text=title))

    cover = CoverSpec(title=title, accent=accent)
    return ZhiScript(title=title, cover=cover, segments=segments)


def parse_script_file(path: str | Path, *, accent: str = "#0071E3") -> ZhiScript:
    md = Path(path).read_text(encoding="utf-8")
    return parse_script(md, accent=accent)
