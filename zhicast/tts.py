"""TTS providers.

``edge-tts`` is the verified, install-and-go default — its boundary stream
drives the subtitle plan directly. Note: edge-tts 7.x dropped per-word
``WordBoundary`` events in favor of ``SentenceBoundary`` (the underlying
Microsoft service changed). We therefore anchor on real sentence timing
(``offset``/``duration`` are 100-nanosecond units; ``// 10000`` → ms, per
mvp_plan.md §4) and distribute the sentence's tokens evenly across that
window — so the safe-area line grouping still has word-ish granularity with
timings anchored to the real TTS clock. If a future edge-tts release restores
``WordBoundary``, it is used verbatim.

``doubao`` / ``qwen`` are selectable behind ``--tts-provider`` but are **not**
implemented in v0.1 — their TTS API shapes are unverified on this machine
(``schema_unverified``), so we refuse cleanly rather than hard-claim a request
shape that may be wrong. They land as the m3 国产 default upgrade.

A deterministic ``stub`` provider generates silent audio + synthetic word
boundaries so the full pipeline (and the test suite) runs offline.
"""

from __future__ import annotations

import asyncio
import re
import shutil
import struct
import subprocess
import wave
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from .model import WordBoundary

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+|[^A-Za-z0-9\s]")


def _tokenize(text: str) -> list[str]:
    """Split into subtitle tokens: ASCII word runs + individual CJK/punct chars."""
    return [t for t in _TOKEN_RE.findall(text) if t.strip()]


def _distribute(tokens: list[str], start_ms: int, duration_ms: int) -> list[WordBoundary]:
    """Distribute tokens evenly across [start_ms, start_ms+duration_ms]."""
    if not tokens or duration_ms <= 0:
        return []
    per = duration_ms / len(tokens)
    out: list[WordBoundary] = []
    cursor = start_ms
    for tok in tokens:
        dur = max(int(round(per)), 30)
        out.append(WordBoundary(text=tok, offset_ms=int(cursor), duration_ms=dur))
        cursor += per
    return out


@dataclass
class SynthesisResult:
    audio_path: str
    audio_format: str  # "mp3" | "wav"
    boundaries: list[WordBoundary]
    duration_ms: int


class TTSProvider(ABC):
    name: str

    @abstractmethod
    async def synthesize(
        self, text: str, *, out_path: Path, voice: str = DEFAULT_VOICE
    ) -> SynthesisResult:
        """Synthesize one segment. ``out_path`` is where the audio is written;
        returns word boundaries (offsets relative to this segment's start)."""
        raise NotImplementedError


def _probe_duration_ms(path: Path) -> int:
    """Measure an audio file's duration in ms via ffprobe (ships with ffmpeg)."""
    if not shutil.which("ffprobe"):
        return 0
    out = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return int(round(float(out.stdout.strip()) * 1000))
    except (ValueError, TypeError):
        return 0


class EdgeTTSProvider(TTSProvider):
    """Microsoft Edge TTS — free, boundary timing, default engine.

    edge-tts 7.x emits ``SentenceBoundary`` (not per-word ``WordBoundary``);
    we anchor on real sentence timing and distribute tokens evenly within
    each sentence so the safe-area grouping has word-ish granularity. If
    ``WordBoundary`` events reappear, they are used verbatim.
    """

    name = "edge"

    async def synthesize(
        self, text: str, *, out_path: Path, voice: str = DEFAULT_VOICE
    ) -> SynthesisResult:
        import edge_tts

        comm = edge_tts.Communicate(text, voice)
        word_boundaries: list[WordBoundary] = []
        sentences: list[tuple[int, int, str]] = []  # (offset_ms, duration_ms, text)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "wb") as f:
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    f.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    word_boundaries.append(
                        WordBoundary(
                            text=chunk["text"],
                            offset_ms=int(chunk["offset"]) // 10000,
                            duration_ms=int(chunk["duration"]) // 10000,
                        )
                    )
                elif chunk["type"] == "SentenceBoundary":
                    sentences.append(
                        (
                            int(chunk["offset"]) // 10000,
                            int(chunk["duration"]) // 10000,
                            chunk["text"],
                        )
                    )
        duration_ms = _probe_duration_ms(out_path)

        if word_boundaries:
            boundaries = word_boundaries
        elif sentences:
            boundaries = []
            for off_ms, dur_ms, stext in sentences:
                boundaries.extend(_distribute(_tokenize(stext), off_ms, dur_ms))
        else:
            # No boundary events at all: distribute tokens across the whole
            # audio window so the segment still gets subtitle cues.
            boundaries = _distribute(_tokenize(text), 0, duration_ms or 1000)
        return SynthesisResult(
            audio_path=str(out_path),
            audio_format="mp3",
            boundaries=boundaries,
            duration_ms=duration_ms,
        )


class StubTTSProvider(TTSProvider):
    """Deterministic offline provider: silent WAV + synthetic word boundaries.

    Used by tests and by ``--tts-provider stub`` so the pipeline is runnable
    without network. Duration scales with text length so concat timings are
    realistic; boundaries are evenly spaced across that duration.
    """

    name = "stub"

    # ~90ms per character + 250ms lead-in — rough Chinese narration cadence.
    PER_CHAR_MS = 90
    LEAD_IN_MS = 250

    async def synthesize(
        self, text: str, *, out_path: Path, voice: str = DEFAULT_VOICE
    ) -> SynthesisResult:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        words = [w for w in text.split() if w] or [text]
        total_ms = self.LEAD_IN_MS + int(len(text) * self.PER_CHAR_MS)
        # silence envelope at 24kHz mono pcm_s16le
        sample_rate = 24000
        n_samples = int(sample_rate * total_ms / 1000)
        with wave.open(str(out_path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sample_rate)
            w.writeframes(struct.pack("<" + "h" * n_samples, *([0] * n_samples)))
        # evenly spaced word boundaries across the narration window
        per_word = (total_ms - self.LEAD_IN_MS) / max(len(words), 1)
        boundaries: list[WordBoundary] = []
        cursor = self.LEAD_IN_MS
        for word in words:
            dur = max(int(round(per_word)), 40)
            boundaries.append(
                WordBoundary(text=word, offset_ms=int(cursor), duration_ms=dur)
            )
            cursor += dur
        return SynthesisResult(
            audio_path=str(out_path),
            audio_format="wav",
            boundaries=boundaries,
            duration_ms=total_ms,
        )


class _UnverifiedProvider(TTSProvider):
    """Base for providers whose API shape is unverified in v0.1.

    Selectable behind ``--tts-provider`` (the flag exists and validates), but
    synthesizing raises a clear error instead of guessing a request shape that
    may be wrong. The m3 milestone wires the real 国产 TTS default.
    """

    name = "unverified-base"

    def __init__(self, name: str, *, m3_note: str) -> None:
        self.name = name
        self._m3_note = m3_note

    async def synthesize(
        self, text: str, *, out_path: Path, voice: str = DEFAULT_VOICE
    ) -> SynthesisResult:
        raise NotImplementedError(
            f"the '{self.name}' TTS provider is not implemented in v0.1 "
            f"({self._m3_note}); use --tts-provider edge (default) or stub "
            "for offline runs. The provider flag is reserved so m3 can ship the "
            "国产 default without breaking the CLI contract."
        )


def get_provider(name: str) -> TTSProvider:
    name = (name or "edge").lower()
    if name == "edge":
        return EdgeTTSProvider()
    if name == "stub":
        return StubTTSProvider()
    if name == "doubao":
        return _UnverifiedProvider(
            "doubao",
            m3_note="volcengine 豆包 TTS API shape is unverified; lands in m3 as the 国产 default",
        )
    if name == "qwen":
        return _UnverifiedProvider(
            "qwen",
            m3_note="qwen TTS API shape is unverified; lands in m3",
        )
    raise ValueError(
        f"unknown TTS provider '{name}'; expected one of edge|stub|doubao|qwen"
    )


def _run_async(coro):
    """Run an async synth call from sync context, reusing a loop if present."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():  # we're already inside an event loop
            raise RuntimeError("synthesize() must be awaited; called from sync inside a running loop")
    except RuntimeError:
        return asyncio.run(coro)
    return asyncio.run(coro)


def synthesize_script(
    script,  # ZhiScript
    *,
    out_dir: Path,
    provider_name: str = "edge",
    voice: str = DEFAULT_VOICE,
) -> "ZhiScript":
    """Fill each segment's start_ms/end_ms/audio_path/boundaries by running
    TTS per segment. Segments are concatenated on the timeline in order.
    """
    from .model import ZhiScript  # local to avoid cycle in type hints

    provider = get_provider(provider_name)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    cursor_ms = 0
    for idx, seg in enumerate(script.segments):
        out_path = out_dir / f"seg_{idx:03d}.{'wav' if provider.name == 'stub' else 'mp3'}"
        result = _run_async(
            provider.synthesize(seg.text, out_path=out_path, voice=voice)
        )
        seg.audio_path = result.audio_path
        seg.boundaries = result.boundaries
        seg.start_ms = cursor_ms
        seg.end_ms = cursor_ms + result.duration_ms
        cursor_ms = seg.end_ms
    return script
