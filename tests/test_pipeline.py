"""ZhiCast m1 pipeline tests — script parse, TTS contract, frame render, SRT,
and an end-to-end build via the stub provider + ffmpeg."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from zhicast.model import (
    SAFE_MAX_LINES,
    Segment,
    WordBoundary,
    ZhiScript,
    CoverSpec,
)
from zhicast.overlay import build_scenes, render_cover, _render_frame
from zhicast.parse import parse_script
from zhicast.render import build_video
from zhicast.subtitle import (
    attach_subtitle_plan,
    build_subtitle_plan,
    display_width,
    write_srt,
)
from zhicast.tts import (
    DEFAULT_VOICE,
    StubTTSProvider,
    get_provider,
    synthesize_script,
)

SAMPLE = """# 为什么大模型记不住对话

## 开场

你有没有发现，和 AI 聊天时它常常忘记你三句话前说过的话。这不是你的错觉。

> "注意力机制的本质是一场受预算约束的回忆。" (认知科学笔记)

## 论证

原因藏在上下文窗口这个概念里。模型一次能看到的 token 数量有上限。

> "超过窗口的内容就像被橡皮擦悄悄抹去。" (技术博客)

## 总结

记住，窗口有限，所以请把关键信息放在最近的位置。
"""


# --------------------------- parse ---------------------------

def test_parse_segments_and_kinds():
    s = parse_script(SAMPLE)
    assert s.title == "为什么大模型记不住对话"
    kinds = [seg.kind for seg in s.segments]
    # titlecards for each ## section + narration + quotes interleaved
    assert kinds.count("titlecard") == 3
    assert kinds.count("quote") == 2
    assert kinds.count("narration") >= 3
    # cover carries the title
    assert s.cover.title == s.title


def test_parse_quote_source_extraction():
    s = parse_script(SAMPLE)
    quotes = [seg for seg in s.segments if seg.kind == "quote"]
    assert len(quotes) == 2
    assert quotes[0].source == "认知科学笔记"
    assert quotes[1].source == "技术博客"
    # quote body should not contain the trailing (来源)
    assert "认知科学笔记" not in quotes[0].text
    assert "（" not in quotes[0].text and "(" not in quotes[0].text


def test_parse_empty_input_falls_back():
    s = parse_script("")
    assert len(s.segments) == 1
    assert s.segments[0].kind == "narration"


# --------------------------- subtitle ---------------------------

def _script_with_boundaries() -> ZhiScript:
    """A narration segment with synthetic word boundaries."""
    words = ["今天", "我们", "来聊一聊", "为什么", "大模型", "记不住", "你", "三句话", "前", "说过的", "内容", "这并不是", "错觉", "而是", "上下文", "窗口", "的", "限制"]
    b: list[WordBoundary] = []
    cursor = 250
    for w in words:
        dur = max(int(len(w) * 200), 80)
        b.append(WordBoundary(text=w, offset_ms=cursor, duration_ms=dur))
        cursor += dur
    seg = Segment(
        kind="narration",
        text="".join(words),
        start_ms=0,
        end_ms=cursor,
        boundaries=b,
    )
    return ZhiScript(title="t", cover=CoverSpec(title="t"), segments=[seg])


def test_subtitle_plan_respects_safe_area():
    s = _script_with_boundaries()
    cues = build_subtitle_plan(s)
    assert len(cues) >= 1
    for cue in cues:
        assert len(cue.lines) <= SAFE_MAX_LINES
        for line in cue.lines:
            assert display_width(line) <= 28  # ≤14 CJK chars/line
        # min on-screen time
        assert cue.end_ms - cue.start_ms >= 800


def _long_sentence_script() -> ZhiScript:
    """58 contiguous CJK chars, no >350ms boundary gap -> one narration run."""
    long_sentence = "上下文窗口是模型一次能看到的全部内容它决定了模型的工作记忆上限超过窗口的对话内容就像被橡皮擦悄悄抹去一样无法再被参考"
    b: list[WordBoundary] = []
    cursor = 250
    for ch in long_sentence:
        b.append(WordBoundary(text=ch, offset_ms=cursor, duration_ms=200))
        cursor += 200
    seg = Segment(kind="narration", text=long_sentence, start_ms=0, end_ms=cursor, boundaries=b)
    return ZhiScript(title="t", cover=CoverSpec(title="t"), segments=[seg])


def test_subtitle_plan_no_text_loss_on_long_sentence():
    # v0.2.0 fix: a cue that overflows the 2-line budget used to silently
    # drop words; now it splits into more cues and keeps every char.
    s = _long_sentence_script()
    long_sentence = s.segments[0].text
    cues = build_subtitle_plan(s)
    assert len(cues) > 1  # budget-split, not one overflowing cue
    joined = "".join(cue.text.replace("\n", "") for cue in cues)
    assert long_sentence in joined.replace(" ", "")
    for cue in cues:  # safe area still holds on every split cue
        assert len(cue.lines) <= SAFE_MAX_LINES
        for line in cue.lines:
            assert display_width(line) <= 28


def test_wrap_hard_splits_wide_tokens():
    # v0.2.0 guard: a single token wider than one safe line (e.g. a spaceless
    # CJK run from a provider) must be hard-split, never overflow a line.
    from zhicast.subtitle import _wrap_to_safe

    giant = "聊天时它常常忘记你三句话前说过的话"  # 17 CJK chars = 34 units
    lines = _wrap_to_safe([giant])
    assert lines
    for line in lines:
        assert display_width(line) <= 28
    assert "".join(lines) == giant  # hard-split keeps every char


def test_subtitle_plan_absolute_timing():
    s = _script_with_boundaries()
    seg = s.segments[0]
    seg.start_ms = 5000  # segment starts 5s into the timeline
    cues = build_subtitle_plan(s)
    assert cues
    # first cue must start at/after segment start + first boundary offset
    assert cues[0].start_ms >= seg.start_ms + seg.boundaries[0].offset_ms - 1


def test_srt_file_is_valid():
    s = attach_subtitle_plan(_script_with_boundaries())
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        p = write_srt(s.subtitle_cues, Path(d) / "video.srt")
        text = p.read_text(encoding="utf-8")
    # at least one numbered cue block with --> arrow and timestamp
    assert "-->" in text
    assert "1\n" in text
    # timestamps look like HH:MM:SS,mmm
    lines = text.strip().splitlines()
    assert ":" in lines[1] and "," in lines[1]


# --------------------------- TTS contract ---------------------------

def test_stub_tts_contract(tmp_path):
    import asyncio

    provider = StubTTSProvider()
    out = tmp_path / "seg.wav"
    result = asyncio.run(provider.synthesize("测试一句旁白", out_path=out, voice=DEFAULT_VOICE))
    assert result.audio_format == "wav"
    assert out.exists() and out.stat().st_size > 0
    assert result.duration_ms > 0
    assert len(result.boundaries) >= 1
    # boundaries are monotonically non-decreasing in offset
    offs = [b.offset_ms for b in result.boundaries]
    assert offs == sorted(offs)
    # last boundary fits within the audio duration
    last = result.boundaries[-1]
    assert last.offset_ms + last.duration_ms <= result.duration_ms + 5


def test_synthesize_script_fills_timings(tmp_path):
    s = parse_script(SAMPLE)
    s = synthesize_script(s, out_dir=tmp_path, provider_name="stub")
    assert s.total_ms > 0
    # every segment got audio + absolute timings, monotonically increasing
    starts = [seg.start_ms for seg in s.segments]
    ends = [seg.end_ms for seg in s.segments]
    assert starts == sorted(starts)
    for seg in s.segments:
        assert seg.audio_path and Path(seg.audio_path).exists()
        assert seg.end_ms > seg.start_ms
    assert s.segments[-1].end_ms == s.total_ms


def test_doubao_qwen_flagged_not_implemented(tmp_path):
    # providers are selectable (flag exists) but refuse cleanly — no fake API shape
    doubao = get_provider("doubao")
    assert doubao.name == "doubao"
    with pytest.raises(NotImplementedError):
        import asyncio

        asyncio.run(doubao.synthesize("x", out_path=tmp_path / "x.wav"))
    qwen = get_provider("qwen")
    with pytest.raises(NotImplementedError):
        import asyncio

        asyncio.run(qwen.synthesize("x", out_path=tmp_path / "y.wav"))


def test_unknown_provider_raises():
    with pytest.raises(ValueError):
        get_provider("nonexistent-engine")


def test_stub_tts_cjk_boundaries_granular(tmp_path):
    # v0.2.0 fix: spaceless CJK used to become ONE giant token that violated
    # the 字幕安全区 line budget; stub now tokenizes per CJK char like the
    # edge SentenceBoundary fallback.
    import asyncio

    text = "你有没有发现和AI聊天时它常常忘记你三句话前说过的话"
    result = asyncio.run(
        StubTTSProvider().synthesize(text, out_path=tmp_path / "seg.wav", voice=DEFAULT_VOICE)
    )
    tokens = [b.text for b in result.boundaries]
    assert len(tokens) > 1  # not one giant token
    for tok in tokens:
        assert display_width(tok) <= 28
    assert "".join(tokens).replace(" ", "") == text.replace(" ", "")
    offs = [b.offset_ms for b in result.boundaries]
    assert offs == sorted(offs)


def test_stub_pipeline_cues_respect_safe_area_and_keep_text(tmp_path):
    # v0.2.0 end-to-end: the README-recommended offline path must produce
    # cues that keep every segment char AND obey the safe-area rule.
    from collections import Counter

    s = synthesize_script(parse_script(SAMPLE), out_dir=tmp_path, provider_name="stub")
    s = attach_subtitle_plan(s)
    assert s.subtitle_cues
    for cue in s.subtitle_cues:
        assert len(cue.lines) <= SAFE_MAX_LINES
        for line in cue.lines:
            assert display_width(line) <= 28
    seg_chars = Counter(
        ch for seg in s.segments for ch in seg.text if not ch.isspace()
    )
    cue_chars = Counter(
        ch for cue in s.subtitle_cues for ch in cue.text if not ch.isspace()
    )
    assert cue_chars == seg_chars  # no subtitle text lost anywhere


def test_run_async_inside_running_loop_raises_clear_error():
    # v0.2.0 fix: _run_async used to swallow its own "must be awaited"
    # RuntimeError and surface asyncio.run's confusing internal error instead.
    import asyncio

    from zhicast.tts import _run_async

    async def inside_loop():
        async def noop():
            return 42

        with pytest.raises(RuntimeError, match="must be awaited"):
            _run_async(noop())

    asyncio.run(inside_loop())


# --------------------------- version surfaces ---------------------------

def test_version_surfaces_agree():
    # v0.2.0 lockstep: VERSION file == package __version__ == pyproject version.
    import tomllib

    repo_root = Path(__file__).resolve().parent.parent
    from zhicast import __version__

    version_file = (repo_root / "VERSION").read_text(encoding="utf-8").strip()
    assert version_file == __version__
    pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == __version__


# --------------------------- overlay frames ---------------------------

def test_cover_renders_png(tmp_path):
    s = attach_subtitle_plan(synthesize_script(parse_script(SAMPLE), out_dir=tmp_path, provider_name="stub"))
    cover = render_cover(s, tmp_path)
    assert cover.exists()
    from PIL import Image

    with Image.open(cover) as im:
        assert im.size == (1920, 1080)


def test_scene_frame_renders_png(tmp_path):
    s = attach_subtitle_plan(synthesize_script(parse_script(SAMPLE), out_dir=tmp_path, provider_name="stub"))
    assert s.subtitle_cues, "stub script should yield subtitle cues"
    cue = s.subtitle_cues[0]
    png = _render_frame(s, cue.start_ms, cue, tmp_path / "one.png")
    from PIL import Image

    with Image.open(png) as im:
        assert im.size == (1920, 1080)


def test_build_scenes_tile_timeline(tmp_path):
    s = attach_subtitle_plan(synthesize_script(parse_script(SAMPLE), out_dir=tmp_path, provider_name="stub"))
    scenes = build_scenes(s, tmp_path)
    assert scenes
    # tiles [0, total] continuously with no gaps
    assert scenes[0].start_ms == 0
    assert scenes[-1].end_ms == s.total_ms
    for a, b in zip(scenes, scenes[1:]):
        assert a.end_ms == b.start_ms


# --------------------------- end-to-end ---------------------------

needs_ffmpeg = pytest.mark.skipif(
    not shutil.which("ffmpeg"), reason="ffmpeg not installed"
)


@needs_ffmpeg
def test_end_to_end_build(tmp_path):
    s = parse_script(SAMPLE)
    s = synthesize_script(s, out_dir=tmp_path / "audio", provider_name="stub")
    s = attach_subtitle_plan(s)
    scenes = build_scenes(s, tmp_path)
    render_cover(s, tmp_path)
    mp4 = build_video(s, scenes, tmp_path)
    assert mp4.exists() and mp4.stat().st_size > 0
    # ffprobe: video + audio streams, 16:9 / 1920x1080, duration > 0
    probe = shutil.which("ffprobe")
    assert probe
    import subprocess

    out = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_entries",
            "stream=codec_type,width,height,duration:format=duration",
            "-of", "json", str(mp4),
        ],
        capture_output=True, text=True, check=True,
    )
    import json

    data = json.loads(out.stdout)
    types = [st["codec_type"] for st in data.get("streams", [])]
    assert "video" in types and "audio" in types
    vstream = next(st for st in data["streams"] if st["codec_type"] == "video")
    assert (vstream.get("width"), vstream.get("height")) == (1920, 1080)
    dur = float(data.get("format", {}).get("duration", 0) or vstream.get("duration", 0))
    assert dur > 0
