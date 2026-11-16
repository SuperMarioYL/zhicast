"""Subtitle cue invariants — timeline and 字幕安全区 line budget.

v0.4.0 fixes pinned here:

  * Cue tails are settled against their neighbours. The 弹幕-rhythm pass used to
    *extend* a cue to next.start - RHYTHM_GAP_MS whenever there was room, so a
    long silence stretched one cue to 22.9s against MAX_CUE_MS (6s). And the
    MIN_CUE_MS widening ignored the next cue, so every short `## section`
    titlecard overlapped the narration cue that followed (the shipped sample
    produced four overlapping pairs; build_scenes renders only the first match,
    so the overlapped cue's opening words never appeared on screen).
  * A single provider token wider than one safe line produced a 3-line cue,
    violating SAFE_MAX_LINES and README.md's "最多两行".
"""

from __future__ import annotations

from zhicast.model import (
    SAFE_MAX_LINES,
    CoverSpec,
    Segment,
    WordBoundary,
    ZhiScript,
)
from zhicast.overlay import build_scenes
from zhicast.subtitle import (
    MAX_CUE_MS,
    build_subtitle_plan,
    display_width,
)


def _bounds(words: list[tuple[str, int, int]]) -> list[WordBoundary]:
    return [
        WordBoundary(text=text, offset_ms=offset, duration_ms=duration)
        for text, offset, duration in words
    ]


def _script(segments: list[Segment]) -> ZhiScript:
    return ZhiScript(title="t", cover=CoverSpec(title="t"), segments=segments)


def _short_titlecard_then_narration() -> ZhiScript:
    """A ~430ms `## section` titlecard followed by narration.

    This is the shape the stub provider produces for the shipped SAMPLE: the
    titlecard cue is widened to MIN_CUE_MS and used to overlap the narration
    cue that starts at 430 + 250ms of lead-in.
    """
    titlecard = Segment(
        kind="titlecard",
        text="开场",
        start_ms=0,
        end_ms=430,
        boundaries=_bounds([("开场", 250, 90), ("场", 340, 90)]),
    )
    narration = Segment(
        kind="narration",
        text="你有没有发现",
        start_ms=430,
        end_ms=3000,
        boundaries=_bounds(
            [("你", 250, 200), ("有", 450, 200), ("没有", 650, 200), ("发现", 850, 200)]
        ),
    )
    return _script([titlecard, narration])


def test_cues_never_overlap_on_short_segment():
    cues = build_subtitle_plan(_short_titlecard_then_narration())
    assert len(cues) >= 2
    for previous, nxt in zip(cues, cues[1:]):
        assert previous.end_ms <= nxt.start_ms, (
            f"cue {previous.index} ends {previous.end_ms}ms but cue {nxt.index} "
            f"starts {nxt.start_ms}ms"
        )
    for cue in cues:
        assert cue.end_ms > cue.start_ms


def _long_silence_script() -> ZhiScript:
    """Two 3s segments separated by a 20s silence (one cue per segment)."""
    first = Segment(
        kind="narration",
        text="第一段旁白内容",
        start_ms=0,
        end_ms=3000,
        boundaries=_bounds(
            [("第一段", 0, 1000), ("旁白", 1000, 1000), ("内容", 2000, 1000)]
        ),
    )
    second = Segment(
        kind="narration",
        text="第二段旁白内容",
        start_ms=23000,
        end_ms=26000,
        boundaries=_bounds(
            [("第二段", 0, 1000), ("旁白", 1000, 1000), ("内容", 2000, 1000)]
        ),
    )
    return _script([first, second])


def test_cue_does_not_linger_past_max_cue_ms():
    cues = build_subtitle_plan(_long_silence_script())
    assert cues
    for cue in cues:
        assert cue.end_ms - cue.start_ms <= MAX_CUE_MS
    # the first cue belongs to the first segment: it must not reach the silence
    assert cues[0].end_ms <= 6000


def _short_trailing_titlecard() -> ZhiScript:
    narration = Segment(
        kind="narration",
        text="旁白",
        start_ms=0,
        end_ms=2000,
        boundaries=_bounds([("旁白", 0, 2000)]),
    )
    ending = Segment(
        kind="titlecard",
        text="尾声",
        start_ms=2000,
        end_ms=2430,
        boundaries=_bounds([("尾声", 0, 430)]),
    )
    return _script([narration, ending])


def test_last_cue_ends_within_timeline(tmp_path):
    script = _short_trailing_titlecard()
    cues = build_subtitle_plan(script)
    assert cues
    assert cues[-1].end_ms <= script.total_ms
    scenes = build_scenes(script.model_copy(update={"subtitle_cues": cues}), tmp_path)
    assert scenes
    assert scenes[-1].end_ms == script.total_ms


# --------------------------- line budget ---------------------------

OVERWIDE = "上下文窗口是模型一次能看到的全部内容它决定了模型的工作记忆上限"  # 34 chars = 68 units


def _overwide_token_script() -> ZhiScript:
    seg = Segment(
        kind="narration",
        text=OVERWIDE,
        start_ms=0,
        end_ms=4000,
        boundaries=_bounds([(OVERWIDE, 0, 4000)]),
    )
    return _script([seg])


def test_overwide_single_token_fans_out_into_budget_cues():
    cues = build_subtitle_plan(_overwide_token_script())
    assert cues
    for cue in cues:
        assert len(cue.lines) <= SAFE_MAX_LINES
        for line in cue.lines:
            assert display_width(line) <= 28
    joined = "".join(cue.text for cue in cues).replace("\n", "")
    assert joined == OVERWIDE
