"""ZhiCast CLI — the m1 entry point.

``zhicast build script.md -o out/`` runs the full pipeline end to end:
parse → TTS → 字幕安全区 cues → Pillow scene frames + cover → ffmpeg →
16:9 MP4 + SRT + cover.png. ``zhicast serve`` wraps the same pipeline in a
local web page (the m2 surface, here as a working preview).
"""

from __future__ import annotations

import json
from pathlib import Path

import typer

from . import __version__
from .overlay import build_scenes, render_cover
from .parse import parse_script_file
from .render import build_video
from .subtitle import attach_subtitle_plan, write_srt
from .tts import DEFAULT_VOICE, synthesize_script

app = typer.Typer(
    name="zhicast",
    help="把B站知识区文字脚本转成16:9横屏知识视频",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def build(
    script: Path = typer.Argument(..., help="markdown 知识区脚本路径"),
    out: Path = typer.Option(Path("out"), "-o", "--out", help="输出目录"),
    provider: str = typer.Option(
        "edge", "--tts-provider", help="TTS 引擎: edge (默认) | stub (离线) | doubao | qwen"
    ),
    voice: str = typer.Option(DEFAULT_VOICE, "--voice", help="TTS 音色 (edge-tts voice id)"),
) -> None:
    """从 markdown 脚本一键生成 16:9 知识区视频。"""
    if not script.exists():
        typer.echo(f"error: script not found: {script}", err=True)
        raise typer.Exit(code=2)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    audio_dir = out / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    typer.echo(f"[1/6] parse script: {script}")
    script_obj = parse_script_file(script)
    typer.echo(f"      title={script_obj.title!r} segments={len(script_obj.segments)}")

    typer.echo(f"[2/6] tts ({provider}, voice={voice})")
    try:
        script_obj = synthesize_script(
            script_obj, out_dir=audio_dir, provider_name=provider, voice=voice
        )
    except NotImplementedError as e:
        # reserved providers (doubao/qwen) report cleanly, like the
        # script-not-found path — never a raw traceback
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(code=2)
    typer.echo(f"      total={script_obj.total_ms/1000:.1f}s")

    typer.echo("[3/6] subtitle plan (字幕安全区)")
    script_obj = attach_subtitle_plan(script_obj)
    srt_path = write_srt(script_obj.subtitle_cues, out / "video.srt")
    typer.echo(f"      cues={len(script_obj.subtitle_cues)} srt={srt_path.name}")

    typer.echo("[4/6] overlay scenes + cover")
    scenes = build_scenes(script_obj, out)
    cover = render_cover(script_obj, out)
    typer.echo(f"      scenes={len(scenes)} cover={cover.name}")

    typer.echo("[5/6] render video (ffmpeg)")
    mp4 = build_video(script_obj, scenes, out)
    typer.echo(f"      mp4={mp4.name}")

    typer.echo("[6/6] done")
    (out / "manifest.json").write_text(
        json.dumps(script_obj.model_dump(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    typer.echo(f"\noutput: {mp4.resolve()}")
    typer.echo(f"  cover:  {cover.resolve()}")
    typer.echo(f"  srt:    {srt_path.resolve()}")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    provider: str = typer.Option("edge", "--tts-provider"),
) -> None:
    """本地 Web 页：贴脚本 → 生成 → 下载 MP4 + 封面。"""
    import uvicorn
    from .web import build_app

    typer.echo(f"zhicast serve → http://{host}:{port}  (tts={provider})")
    uvicorn.run(build_app(provider=provider), host=host, port=port)


@app.command()
def version() -> None:
    """打印版本号。"""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
