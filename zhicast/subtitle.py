"""Subtitle plan — 字幕安全区-constrained cues + SRT.

The moat-carrying step (mvp_plan.md §2): word-boundary timestamps from TTS are
grouped into cues that obey B站's 16:9 字幕安全区 rules — each line ≤ 14 CJK
chars (measured as 28 CJK-width units, ASCII = 1 unit), ≤ 2 lines, with small
弹幕-rhythm breathing gaps between cues so the bottom safe area isn't a wall of
text. No forced-alignment ML step — the timing is read directly from TTS.
"""

from __future__ import annotations

import unicodedata
from datetime import timedelta
from pathlib import Path

import srt

from .model import (
    SAFE_MAX_LINES,
    SubtitleCue,
    WordBoundary,
    ZhiScript,
)

# 14 CJK chars/line, CJK = 2 units, ASCII = 1 unit → 28 units/line.
SAFE_LINE_UNITS = 28
# 弹幕-rhythm: a small gap between adjacent cues so the safe area breathes.
RHYTHM_GAP_MS = 120
# Minimum on-screen time for a cue (readability floor).
MIN_CUE_MS = 800
# Hard cap so a single cue never lingers past ~6s.
MAX_CUE_MS = 6000


def _is_cjk(ch: str) -> bool:
    return unicodedata.east_asian_width(ch) in ("W", "F")


def display_width(s: str) -> int:
    """CJK-width units: full-width chars count 2, others 1."""
    return sum(2 if _is_cjk(ch) else 1 for ch in s)


def _join_words(words: list[str]) -> str:
    """Join TTS boundary words: space if all ASCII, no-space once CJK appears."""
    if all(not _is_cjk(ch) for w in words for ch in w):
        return " ".join(words)
    return "".join(words)


def _split_wide_token(token: str) -> list[str]:
    """Hard-split a token wider than one safe line. Any provider can emit a
    token that already violates the line budget (e.g. a spaceless CJK run);
    the safe-area rule must hold by construction, not by provider courtesy."""
    if display_width(token) <= SAFE_LINE_UNITS:
        return [token]
    parts: list[str] = []
    cur = ""
    for ch in token:
        if cur and display_width(cur + ch) > SAFE_LINE_UNITS:
            parts.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        parts.append(cur)
    return parts


def _wrap_to_safe(words: list[str]) -> list[str]:
    """Greedy wrap into lines of ≤ SAFE_LINE_UNITS each; never drops text
    (extra lines are the caller's cue-splitting signal, see build_subtitle_plan)."""
    words = [part for w in words for part in _split_wide_token(w)]
    lines: list[list[str]] = []
    current: list[str] = []
    current_units = 0
    for w in words:
        sep = 1 if (current and all(not _is_cjk(c) for c in "".join(current) + w)) else 0
        w_units = display_width(w) + sep
        if current and current_units + w_units > SAFE_LINE_UNITS:
            lines.append(current)
            current = [w]
            current_units = display_width(w)
        else:
            current.append(w)
            current_units += w_units
    if current:
        lines.append(current)
    return [_join_words(line) for line in lines if line]


def _fits_cue_budget(pending: list[str], word: str) -> bool:
    """Would pending + word still wrap within SAFE_MAX_LINES lines?"""
    return len(_wrap_to_safe([*pending, word])) <= SAFE_MAX_LINES


def _timed_pieces(b: WordBoundary) -> list[tuple[int, int, str]]:
    """Split a boundary wider than one safe line into timed pieces.

    The cue loop can start a new cue between words but cannot split one word, so
    a single over-wide token (e.g. a spaceless CJK run) would wrap past
    SAFE_MAX_LINES inside one cue. Each piece is at most SAFE_LINE_UNITS wide, so
    the budget check above keeps every cue at <= SAFE_MAX_LINES lines by
    construction. The boundary's audio window is divided evenly across the
    pieces — the same distribution rule the TTS sentence fallback uses.
    """
    parts = _split_wide_token(b.text)
    if len(parts) == 1:
        return [(b.offset_ms, b.duration_ms, b.text)]
    pieces: list[tuple[int, int, str]] = []
    for k, part in enumerate(parts):
        start = b.offset_ms + (b.duration_ms * k) // len(parts)
        end = b.offset_ms + (b.duration_ms * (k + 1)) // len(parts)
        pieces.append((start, max(end - start, 1), part))
    return pieces


def _settle_cue_timings(cues: list[SubtitleCue], total_ms: int) -> list[SubtitleCue]:
    """Settle cue tails so the timeline invariants hold.

    MIN_CUE_MS/MAX_CUE_MS shape a cue while it is built, but nothing there knows
    the next cue: a short segment widened to the readability floor can overlap
    the cue that follows, and the last cue can run past the video. This pass only
    ever trims — cue i ends at or before cue i+1, never after the end of the
    timeline, and leaves a 弹幕-rhythm gap when it still clears MIN_CUE_MS.
    """
    for i, cue in enumerate(cues):
        hard_end = cues[i + 1].start_ms if i + 1 < len(cues) else total_ms
        end = min(cue.end_ms, hard_end)
        gap_end = hard_end - RHYTHM_GAP_MS
        if gap_end > cue.start_ms + MIN_CUE_MS:
            end = min(end, gap_end)
        end = max(end, cue.start_ms)
        if end != cue.end_ms:
            cues[i] = cue.model_copy(update={"end_ms": end})
    return cues


def build_subtitle_plan(script: ZhiScript) -> list[SubtitleCue]:
    """Build safe-area-constrained cues from every segment's word boundaries.

    Cue timings are absolute on the video timeline (segment.start_ms +
    boundary.offset_ms). Inter-cue gaps preserve 弹幕 rhythm.
    """
    cues: list[SubtitleCue] = []
    idx = 0
    pending_words: list[tuple[int, int, str]] = []  # (offset_ms, dur_ms, text)

    def flush(current_start: int | None, current_end: int) -> None:
        nonlocal idx
        if not pending_words or current_start is None:
            pending_words.clear()
            return
        words = [w[2] for w in pending_words]
        lines = _wrap_to_safe(words)
        if not lines:
            pending_words.clear()
            return
        start = current_start
        end = max(current_end, start + MIN_CUE_MS)
        end = min(end, start + MAX_CUE_MS)
        cues.append(
            SubtitleCue(index=idx, start_ms=start, end_ms=end, lines=lines)
        )
        idx += 1
        pending_words.clear()

    for seg in script.segments:
        if not seg.boundaries:
            continue
        cue_start: int | None = None
        cue_end = 0
        for b in seg.boundaries:
            for off_ms, dur_ms, text in _timed_pieces(b):
                abs_off = seg.start_ms + off_ms
                abs_end = abs_off + dur_ms
                # sentence-ish break: a long silence gap closes the current cue
                if pending_words and cue_start is not None and abs_off - cue_end > 350:
                    flush(cue_start, cue_end)
                    cue_start = None
                # line budget: a cue holds at most SAFE_MAX_LINES wrapped lines —
                # close it and let the word start the next cue instead of dropping it
                if cue_start is not None and not _fits_cue_budget(
                    [w[2] for w in pending_words], text
                ):
                    flush(cue_start, cue_end)
                    cue_start = None
                if cue_start is None:
                    cue_start = abs_off
                cue_end = abs_end
                pending_words.append((off_ms, dur_ms, text))
        flush(cue_start, cue_end)

    return _settle_cue_timings(cues, script.total_ms)


def attach_subtitle_plan(script: ZhiScript) -> ZhiScript:
    cues = build_subtitle_plan(script)
    return script.model_copy(update={"subtitle_cues": cues})


def write_srt(cues: list[SubtitleCue], out_path: str | Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    subs = [
        srt.Subtitle(
            index=c.index + 1,
            start=timedelta(milliseconds=c.start_ms),
            end=timedelta(milliseconds=c.end_ms),
            content=c.text,
        )
        for c in cues
    ]
    out_path.write_text(srt.compose(subtitles=subs, reindex=False), encoding="utf-8")
    return out_path
