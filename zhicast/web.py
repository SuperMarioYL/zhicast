"""Local web surface (m2 preview).

A single FastAPI page that wraps the same parse→tts→subtitle→overlay→render
pipeline as the CLI: paste a markdown script, click 生成, download the MP4 +
cover. The full 知识区-format web UI (引用标注 cards editor, 封面 templates,
batch series) is the m2 milestone; this is a working local preview of the m1
engine so ``zhicast serve`` demonstrates the happy path end to end.
"""

from __future__ import annotations

import html
import tempfile
import uuid
from pathlib import Path

from fastapi import FastAPI, Form
from fastapi.responses import FileResponse, HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .overlay import build_scenes, render_cover
from .parse import parse_script
from .render import build_video
from .subtitle import attach_subtitle_plan, write_srt
from .tts import DEFAULT_VOICE, synthesize_script

_TEMPLATE_DIR = Path(__file__).parent / "templates"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def _index_html(message: str = "", error: str = "") -> str:
    return _env().get_template("index.html").render(message=message, error=error)


def _result_html(job_id: str, title: str, total_s: float, cues: int) -> str:
    safe_title = html.escape(title)
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>ZhiCast — {safe_title}</title>
<style>body{{font-family:-apple-system,"PingFang SC",sans-serif;background:#0E0E12;color:#F5F5F7;margin:0;padding:32px}}
a{{color:#4DA3FF}}.wrap{{max-width:960px;margin:0 auto}}
video{{width:100%;border-radius:12px;background:#000}}</style></head>
<body><div class="wrap">
<h1>✅ 生成完成 — {safe_title}</h1>
<p>时长 {total_s:.1f}s · 字幕 {cues} 条</p>
<video controls preload="metadata">
  <source src="/files/{job_id}/video.mp4" type="video/mp4">
</video>
<p>
  <a href="/files/{job_id}/video.mp4" download>下载 MP4</a> ·
  <a href="/files/{job_id}/cover.png" download>下载封面 PNG</a> ·
  <a href="/files/{job_id}/video.srt" download>下载 SRT 字幕</a>
</p>
<p><a href="/">← 再做一个</a></p>
</div></body></html>"""


def build_app(*, provider: str = "edge", jobs_root: str | Path | None = None) -> FastAPI:
    app = FastAPI(title="ZhiCast")
    jobs_root = Path(jobs_root) if jobs_root else Path(
        tempfile.mkdtemp(prefix="zhicast_jobs_")
    )
    jobs_root.mkdir(parents=True, exist_ok=True)

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _index_html()

    @app.post("/generate", response_class=HTMLResponse)
    def generate(script: str = Form(...), voice: str = Form(DEFAULT_VOICE)) -> str:
        job_id = uuid.uuid4().hex[:12]
        out = jobs_root / job_id
        out.mkdir(parents=True, exist_ok=True)
        try:
            s = parse_script(script)
            s = synthesize_script(
                s, out_dir=out / "audio", provider_name=provider, voice=voice
            )
            s = attach_subtitle_plan(s)
            write_srt(s.subtitle_cues, out / "video.srt")
            scenes = build_scenes(s, out)
            render_cover(s, out)
            build_video(s, scenes, out)
            return _result_html(
                job_id, s.title, s.total_ms / 1000, len(s.subtitle_cues)
            )
        except Exception as e:  # surface the error on the page for the local tool
            return _index_html(error=f"{type(e).__name__}: {e}")

    @app.get("/files/{job_id}/video.mp4")
    def dl_video(job_id: str) -> FileResponse:
        p = jobs_root / job_id / "video.mp4"
        if not p.exists():
            raise FileNotFoundError(p)
        return FileResponse(p, media_type="video/mp4", filename="video.mp4")

    @app.get("/files/{job_id}/cover.png")
    def dl_cover(job_id: str) -> FileResponse:
        p = jobs_root / job_id / "cover.png"
        if not p.exists():
            raise FileNotFoundError(p)
        return FileResponse(p, media_type="image/png", filename="cover.png")

    @app.get("/files/{job_id}/video.srt")
    def dl_srt(job_id: str) -> FileResponse:
        p = jobs_root / job_id / "video.srt"
        if not p.exists():
            raise FileNotFoundError(p)
        return FileResponse(p, media_type="text/plain", filename="video.srt")

    return app
