<div align="right"><sub><b>English</b>&nbsp;&nbsp;⇄&nbsp;&nbsp;<a href="./README.md">简体中文</a></sub></div>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/hero-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./assets/hero-light.svg">
  <img src="./assets/hero-light.svg" width="880" alt="ZhiCast — script to 知识区 video">
</picture>

<p align="center"><sub>ZhiCast is the open-source tool that brings agent-driven script-to-video to the B站 知识区 16:9 landscape format.</sub></p>

<p align="center">
  <a href="./LICENSE"><img src="https://img.shields.io/github/license/SuperMarioYL/zhicast?color=blue" alt="license"></a>
  <a href="https://github.com/SuperMarioYL/zhicast/releases"><img src="https://img.shields.io/github/v/release/SuperMarioYL/zhicast?color=blue" alt="release"></a>
  <a href="https://github.com/SuperMarioYL/zhicast/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/SuperMarioYL/zhicast/ci.yml?branch=main&label=ci" alt="ci"></a>
  <img src="https://img.shields.io/badge/python-3.12-3776AB" alt="python">
  <img src="https://img.shields.io/badge/launch-Show%20HN-ff6155" alt="Show HN">
  <img src="https://img.shields.io/badge/built%20for-Agent-5E5CE6" alt="Agent">
</p>

**Paste a markdown script, get a B站 知识区 16:9 video with TTS narration, burned-in subtitles and 引用 callouts — no timeline, no Coding Agent.**

---

## Why now

ZhiCast lands the agent-driven script-to-video capability — proven by [OpenMontage](https://github.com/calesthio/OpenMontage) (45K★, "agentic video production system") and [hyperframes](https://github.com/heygen-com/hyperframes) (39K★, "Write HTML. Render video. Built for agents") — on the B站 知识区 surface, without the Coding Agent lock-in those tools require (the CLI/agent workflow that projects like [headroomlabs-ai/headroom](https://github.com/headroomlabs-ai/headroom) sit inside). The same agent-editable-video pain already surfaced on Show HN ([OpenEdit](https://github.com/veedstudio/open-edit), where [@luca-ctx](https://github.com/luca-ctx) and similar posters engaged); ZhiCast launches there too, but takes plain markdown instead of HTML, and encodes 知识区 format rules (字幕安全区 / 引用标注 / 弹幕节奏 / hook→argument→summary pacing) that a generic Agent platform like [langgenius/dify](https://github.com/langgenius/dify) structurally will not. A non-technical UP主 pastes a script and gets a shippable 16:9 video.

<h2><img src="https://api.iconify.design/tabler:topology-star-3.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> Architecture</h2>

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./assets/atlas-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./assets/atlas-light.svg">
  <img src="./assets/atlas-light.svg" width="880" alt="ZhiCast architecture: script→parse→tts→subtitle+overlay→render→MP4">
</picture>

A single Python process, no microservices. The CLI and the web UI reuse the same `parse → tts → subtitle → overlay → render` chain. Subtitle safe-area and 引用/section overlays are rendered to PNG frames by Pillow and sequenced by ffmpeg, so the pipeline runs even on a minimal ffmpeg build without libass.

<h2><img src="https://api.iconify.design/tabler:download.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> Install</h2>

Requires Python 3.12+ and ffmpeg (the `overlay` filter is enough; subtitles are pre-burned into PNG frames, so libass is not required).

```bash
# macOS
brew install ffmpeg
# Debian/Ubuntu
sudo apt install ffmpeg

pip install zhicast
```

<h2><img src="https://api.iconify.design/tabler:rocket.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> Quickstart</h2>

```bash
git clone https://github.com/SuperMarioYL/zhicast.git && cd zhicast
pip install -e ".[dev]"
zhicast build examples/sample_script.md -o out/ --tts-provider stub
```

`--tts-provider stub` uses an offline silent engine so the whole pipeline runs without network. Swap to the default `edge` (needs network) for real TTS narration.

<details><summary>Sample output</summary>

```
[1/6] parse script: examples/sample_script.md
      title='为什么大模型记不住你三句话前说过的话' segments=9
[2/6] tts (stub, voice=zh-CN-XiaoxiaoNeural)
      total=18.4s
[3/6] subtitle plan (字幕安全区)
      cues=9 srt=video.srt
[4/6] overlay scenes + cover
      scenes=18 cover=cover.png
[5/6] render video (ffmpeg)
      mp4=video.mp4
[6/6] done
output: out/video.mp4
```
</details>

<h2><img src="https://api.iconify.design/tabler:terminal-2.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> Usage</h2>

One-command build (default edge-tts, real narration):

```bash
zhicast build script.md -o out/
```

Switch voice or preview offline:

```bash
zhicast build script.md -o out/ --tts-provider edge --voice zh-CN-YunxiNeural
zhicast build script.md -o out/ --tts-provider stub          # offline, no network
```

Local web page (paste script → generate → download MP4 + cover + SRT):

```bash
zhicast serve --port 8000          # http://127.0.0.1:8000
```

Script conventions: `# title` → cover title; `## section` → section title card; `> quote (source)` → 引用 callout card; plain paragraphs → TTS narration. See [`examples/sample_script.md`](./examples/sample_script.md).

<h2><img src="https://api.iconify.design/tabler:photo.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> Demo</h2>

![demo](assets/demo.gif)

The full path from a markdown script to a 16:9 知识区 video: paste script → TTS narration + subtitle-safe-area burn-in + 引用 callout cards → output MP4 and cover. Re-render via [`docs/demo.tape`](./docs/demo.tape) and the [demo workflow](./.github/workflows/demo.yml).

<h2><img src="https://api.iconify.design/tabler:adjustments.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> Configuration</h2>

| Option | Default | Meaning |
|---|---|---|
| `--tts-provider` | `edge` | TTS engine: `edge` (online, default) / `stub` (offline silent) / `doubao` / `qwen` (v0.2+, CN default) |
| `--voice` | `zh-CN-XiaoxiaoNeural` | edge-tts voice id (e.g. `zh-CN-YunxiNeural`, male) |
| `--out` | `out/` | output dir (holds `video.mp4` / `cover.png` / `video.srt` / `manifest.json`) |
| subtitle safe area | 1920×1080 bottom | ≤14 CJK chars/line, ≤2 lines, bottom safe area, 弹幕-rhythm gaps |
| render params | 30fps · crf 23 · yuv420p · aac 192k | see `RenderSpec` (`zhicast/model.py`) |

<h2><img src="https://api.iconify.design/tabler:map-2.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> Roadmap</h2>

- [x] **m1 build pipeline** — markdown → edge-tts (sentence-level timestamps) → subtitle-safe-area SRT → Pillow frames + cover → ffmpeg → 16:9 MP4, end-to-end via `zhicast build`
- [ ] **m2 知识区 format surface** — 引用 callout cards + section title cards + cover templates + local web page (paste→generate→download); the demonstrable MVP
- [ ] **m3 launch readiness** — 30s demo GIF + 豆包 TTS provider (CN default) + Gitee mirror; Show HN / V2EX-ready
- [ ] **v0.2 hosted cloud-render tier** — zero-install, 豆包 high-quality voices, premium cover templates, batch series rendering

<h2><img src="https://api.iconify.design/tabler:credit-card.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> Pricing</h2>

The local engine is fully open-source, free, and commercially usable — but you have to install Python and ffmpeg yourself, which most non-technical UP主 will not.

The **hosted cloud-render tier (v0.2, paid)** fixes that: paste a script in the browser → cloud render (bundled ffmpeg + 豆包 high-quality voices + curated cover templates + batch) → download a finished video, zero local install. Price **¥29/month** (~10 episodes/mo) or a **¥1–2/episode** credit pack. This is the "here's my credit card" path for small studio UP主 teams (multiple 5–15 min episodes/week) — high volume, and the 3–6h/episode edit cost is their sharpest pain. The local OSS engine ships first to prove demand; the first paying customer triggers v0.1 → v0.2.

<h2><img src="https://api.iconify.design/tabler:arrows-exchange.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> vs. a generic Agent platform</h2>

Positioning vs. [langgenius/dify](https://github.com/langgenius/dify):

| Axis | ZhiCast | dify (generic Agent platform) |
|---|---|---|
| Target user | B站 知识区 UP主 (non-technical) | developers / engineering teams |
| Input | paste markdown script | API / workflow orchestration |
| Output | 16:9 知识区 MP4 + cover + SRT | generic agent apps |
| TTS timestamps → subtitles | ✓ (edge-tts sentence-level, no forced-alignment) | — |
| 知识区 format rules | ✓ (字幕安全区 / 引用标注 / 弹幕 rhythm) | — |
| Ecosystem / extensibility | ✗ (single-purpose) | ✓ (rich agent ecosystem, plugins) |

dify beats ZhiCast handily on ecosystem breadth — it is a general agent platform; ZhiCast is a single-purpose vertical video tool. ZhiCast does not compete head-on; it lands the agent-driven script-to-video idea that dify represents onto the B站 知识区 format surface that dify structurally will not cover.

<h2><img src="https://api.iconify.design/tabler:share-2.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> Share this</h2>

```
ZhiCast — the script-to-video tool for B站 知识区. Built for the Agent era, without a Coding Agent. Paste markdown → TTS narration + aligned subtitles + 引用 cards → 16:9 MP4. https://github.com/SuperMarioYL/zhicast
```

<h2><img src="https://api.iconify.design/tabler:license.svg?color=%230071E3&width=24" height="22" align="absmiddle" alt=""> License</h2>

MIT, see [LICENSE](./LICENSE). File issues or PRs at [issues](https://github.com/SuperMarioYL/zhicast/issues).

<p align="center"><sub><a href="./LICENSE">MIT</a> © 2026 SuperMarioYL</sub></p>
