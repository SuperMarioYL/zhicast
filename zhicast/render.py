"""Render — sequence PNG scenes + concat audio into a 16:9 MP4.

Pipeline (mvp_plan.md §4):

  segment audio (mp3/wav) → normalize to uniform wav (ffmpeg-python)
                              → concat demuxer → full audio
  scene PNGs (from overlay) → concat demuxer with per-frame durations
                              → video stream
  video + audio → ffmpeg mux (libx264 + aac, 1920x1080, 30fps, yuv420p)
                → 16:9 MP4 + sidecar SRT

Uses the always-available ``concat`` demuxer + ``overlay``-family compositing
so the pipeline runs even on minimal ffmpeg builds without libass/drawtext
(the subtitles are already burned into the PNG scenes by ``overlay.py``).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import ffmpeg  # ffmpeg-python: audio normalization transcode

from .model import ZhiScript
from .overlay import Scene


def _ffmpeg_bin() -> str:
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError(
            "ffmpeg not found on PATH; install it (e.g. `brew install ffmpeg` or "
            "`apt install ffmpeg`) — ZhiCast needs it to composite the MP4."
        )
    return ff


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(
        cmd, capture_output=True, text=True, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed (rc={proc.returncode}):\ncommand: {' '.join(cmd)}\n"
            f"stderr:\n{proc.stderr[-2000:]}"
        )


def _normalize_audio(script: ZhiScript, out_dir: Path) -> list[Path]:
    """Normalize each segment's audio to uniform 24kHz mono pcm_s16le wav so
    the concat demuxer can join them losslessly (``-c copy``)."""
    norm: list[Path] = []
    for i, seg in enumerate(script.segments):
        if not seg.audio_path or not Path(seg.audio_path).exists():
            continue
        out = out_dir / f"seg_{i:03d}.norm.wav"
        (
            ffmpeg.input(seg.audio_path)
            .output(str(out), ar=24000, ac=1, acodec="pcm_s16le")
            .overwrite_output()
            .run(capture_stdout=True, capture_stderr=True, quiet=True)
        )
        norm.append(out)
    return norm


def _concat_audio(norm_paths: list[Path], out_path: Path) -> Path | None:
    if not norm_paths:
        return None
    list_file = out_path.parent / "audio_concat.txt"
    list_file.write_text(
        "".join(f"file '{p.absolute()}'\n" for p in norm_paths), encoding="utf-8"
    )
    _run(
        [
            _ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy", str(out_path),
        ]
    )
    return out_path


def build_video(
    script: ZhiScript,
    scenes: list[Scene],
    out_dir: str | Path,
) -> Path:
    """Composite scenes + audio → ``<out_dir>/video.mp4`` (16:9, 30fps)."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ff = _ffmpeg_bin()
    rs = script.render

    # 1) audio
    norm = _normalize_audio(script, out_dir)
    audio_path = _concat_audio(norm, out_dir / "audio.wav")

    # 2) frames concat list (per-image durations; last image repeated)
    if not scenes:
        raise RuntimeError("no scenes to render — check that TTS produced audio")
    list_file = out_dir / "frames_concat.txt"
    lines: list[str] = []
    for sc in scenes:
        lines.append(f"file '{Path(sc.png_path).absolute()}'")
        lines.append(f"duration {sc.duration_ms / 1000:.3f}")
    # concat demuxer quirk: the final entry is held until end (no duration line)
    lines.append(f"file '{Path(scenes[-1].png_path).absolute()}'")
    list_file.write_text("\n".join(lines) + "\n", encoding="utf-8")

    out_mp4 = out_dir / "video.mp4"
    cmd = [
        ff, "-y", "-hide_banner", "-loglevel", "error",
        "-f", "concat", "-safe", "0", "-i", str(list_file),
    ]
    if audio_path and audio_path.exists():
        cmd += ["-i", str(audio_path)]
    cmd += [
        "-c:v", rs.video_codec,
        "-pix_fmt", rs.pix_fmt,
        "-r", str(rs.fps),
        "-crf", str(rs.crf),
        "-vf", f"scale={rs.width}:{rs.height}",
    ]
    if audio_path and audio_path.exists():
        cmd += ["-c:a", rs.audio_codec, "-b:a", "192k", "-shortest"]
    cmd += ["-movflags", "+faststart", str(out_mp4)]
    _run(cmd)
    return out_mp4
