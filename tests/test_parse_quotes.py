"""Quote parsing — consecutive `>` lines are one blockquote / one card.

v0.4.0 fix: the parser consumed exactly one `>` line per quote segment, so a
two-line blockquote became two cards, and the first card fell back to the
current `## section` heading as its source — a visible mis-attribution on the
rendered 引用 card. CommonMark treats the run as a single blockquote.
"""

from __future__ import annotations

from zhicast.parse import parse_script

BLOCK = """# 标题

## 论证

> 第一行引用内容
> 第二行引用内容 (某本书)

正文。
"""


def test_multiline_blockquote_is_one_card():
    s = parse_script(BLOCK)
    quotes = [seg for seg in s.segments if seg.kind == "quote"]
    assert len(quotes) == 1
    assert "第一行引用内容" in quotes[0].text
    assert "第二行引用内容" in quotes[0].text
    # the block's own citation wins; the section heading must not be attributed
    assert quotes[0].source == "某本书"


def test_single_line_blockquote_unchanged():
    s = parse_script("# T\n\n## 章节\n\n> 单独引用 (来源A)\n\n> 无来源引用\n")
    quotes = [seg for seg in s.segments if seg.kind == "quote"]
    assert [q.source for q in quotes] == ["来源A", "章节"]
    assert quotes[0].text == "单独引用"


def test_narration_paragraphs_survive_blockquote():
    s = parse_script("# T\n\n前一段。\n\n> 引用\n\n后一段。\n")
    assert [seg.kind for seg in s.segments] == ["narration", "quote", "narration"]
