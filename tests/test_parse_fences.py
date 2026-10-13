"""Parser fence handling — fenced code blocks must never become structure.

v0.3.0 fix: a `# comment` inside a ``` fence used to be parsed as the script
title (cover corruption) and the fence markers leaked into narration text.
"""

from __future__ import annotations

from zhicast.parse import parse_script

SCRIPT = """# 编程知识视频

## 代码示例

下面是关键实现：

```python
# 这只是代码注释，不是章节标题
def main():
    print("hello")
```

以上就是全部内容。
"""


def test_fenced_heading_never_becomes_title():
    s = parse_script(SCRIPT)
    # the real H1 wins; the fenced `#` comment must not
    assert s.title == "编程知识视频"
    assert s.cover.title == s.title


def test_fenced_content_never_becomes_structure():
    s = parse_script(SCRIPT)
    kinds = [seg.kind for seg in s.segments]
    # only the real `## 代码示例` becomes a titlecard, no quote from the fence
    assert kinds.count("titlecard") == 1
    assert kinds.count("quote") == 0
    # the fenced `#` comment is narration text, never a card
    cards = [seg.text for seg in s.segments if seg.kind != "narration"]
    assert "这只是代码注释，不是章节标题" not in cards


def test_fence_markers_do_not_leak_into_segments():
    s = parse_script(SCRIPT)
    for seg in s.segments:
        assert "```" not in seg.text


def test_fenced_code_text_is_preserved_as_narration():
    # nothing is silently dropped: the code body stays in the narration flow
    s = parse_script(SCRIPT)
    narration = " ".join(seg.text for seg in s.segments if seg.kind == "narration")
    assert 'print("hello")' in narration
    assert "def main():" in narration


def test_unfenced_structure_still_parses():
    s = parse_script("# 标题\n\n## 章节\n\n> 引用 (来源)\n\n正文。\n")
    assert s.title == "标题"
    kinds = [seg.kind for seg in s.segments]
    assert kinds.count("titlecard") == 1
    assert kinds.count("quote") == 1


def test_unmatched_fence_degrades_to_narration():
    # an odd number of ``` markers must not corrupt structure either
    md = "# 真标题\n\n```\n# 不是标题\n\n更多内容\n"
    s = parse_script(md)
    assert s.title == "真标题"
    narration = " ".join(seg.text for seg in s.segments if seg.kind == "narration")
    assert "不是标题" in narration
