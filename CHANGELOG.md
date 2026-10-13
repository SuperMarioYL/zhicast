# Changelog

All notable changes to ZhiCast are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[SemVer](https://semver.org/).

## [0.3.0] — 2026-10-14

### Fixed

- **Release 资产真正附到 GitHub Release**：release 工作流此前构建 dist/ 后只上传
  CI artifact，Release 页面资产始终为空；现在新增 attach 步骤，用
  `gh release upload --clobber` 把 wheel/sdist/checksums 附到对应 Release
  （Release 尚不存在时自动创建）。
- **围栏代码块不再被解析成脚本结构**：``` 代码块内的 `# 注释` 此前会成为脚本
  标题（封面随之被改写），``` 标记行也会泄漏进旁白文本；现在围栏内一律按普通
  旁白处理，围栏标记行丢弃，无围栏脚本解析行为不变。
- **用户面失败改为干净报错**：`zhicast serve` 所需的 python-multipart 随包声明，
  `pip install` 后开箱即用（不再需要 README 中的手动补装步骤）；Web 下载接口对
  不存在的 job 返回 404 而不是 500；`--tts-provider doubao|qwen` 输出一行清晰
  错误并以退出码 2 结束，不再抛出整屏 traceback。

### Changed

- 长引用卡片自适应字号：引用卡片超过画布高度时按 40→24px 阶梯缩小字号并重排，
  病理超长输入钳制在画布内起始；短引用渲染与旧版逐像素一致。
- 版本号全表面 lockstep 升至 0.3.0：`VERSION`、`pyproject.toml`、
  `zhicast.__version__`、README/README.en 徽标行、`web/site.json`
  （`meta.content_version` + `footer.tag`）。

## [0.2.0] — 2026-09-09

### Fixed

- **字幕安全区 cue 不再丢词**：长句（>14 CJK 字且无 >350ms 停顿） previously
  落入单条 cue 后，超出行预算（2 行 × 28 单位）的词被静默丢弃 —— 58 字连续旁白
  只剩 28 字字幕。现在按行预算切分 cue：全部旁白文本都进入字幕，且每条 cue 仍
  满足 ≤2 行、每行 ≤14 CJK 字（28 单位）的安全区约束。
- **stub TTS 的 CJK 边界违反字幕安全区**：无空格中文整句此前成为一个巨型
  token（实测输出 50 单位行），违反每行 ≤28 单位契约；stub 现在与 edge 的
  SentenceBoundary 回退共用分词（CJK 逐字粒度），并在折行处对超宽 token 硬切分，
  使安全区约束按构造成立。`--tts-provider stub` 离线端到端字幕恢复正确。
- **`_run_async` 不再吞掉自己的清晰报错**：在运行中的 event loop 内调用时，
  原实现抛出的 "must be awaited" RuntimeError 被自身 except 捕获，转而暴露
  费解的 `asyncio.run() cannot be called from a running event loop` 并泄漏
  never-awaited 协程；现改用 `asyncio.get_running_loop()` 检测并直接给出清晰
  错误，同时消除 Python 3.12 下 `get_event_loop` 的弃用告警。

### Changed

- 版本号全表面 lockstep 升至 0.2.0：`VERSION`、`pyproject.toml`、
  `zhicast.__version__`、README/README.en 徽标行、`web/site.json`
  （`meta.content_version` + `footer.tag`）；sdist 现在附带 CHANGELOG.md。

## [0.1.0] — 2026-08-06

### Added

- m1 构建管线：`zhicast build script.md -o out/` 一条命令从 markdown 知识区
  脚本生成 16:9 MP4 —— edge-tts 配音（句级时间戳驱动字幕）、字幕安全区 SRT、
  Pillow 场景帧 + 封面、ffmpeg 合成；`stub` 离线引擎可无网络跑通全管线。
- m2 知识区格式面：引用标注卡片、章节标题卡、字幕安全区底部布局、16:9 封面
  PNG；`zhicast serve` 本地 Web 页（贴脚本 → 生成 → 下载 MP4/封面/SRT）。
- 双语 README（中文主文档 + README.en.md）、CI（pytest + ffmpeg）、
  demo GIF（vhs）、GitHub Pages 产品站。

[0.3.0]: https://github.com/SuperMarioYL/zhicast/releases/tag/v0.3.0
[0.2.0]: https://github.com/SuperMarioYL/zhicast/releases/tag/v0.2.0
[0.1.0]: https://github.com/SuperMarioYL/zhicast/releases/tag/v0.1.0
