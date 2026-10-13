"""Web/CLI surface error handling — user-facing surfaces fail cleanly.

v0.3.0 fixes pinned here:
  * stale/unknown download links return 404, not a 500 from an unhandled
    FileNotFoundError;
  * `zhicast build --tts-provider doubao|qwen` (selectable but unimplemented)
    exits 2 with a clean error line instead of a raw traceback.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from zhicast.cli import app
from zhicast.web import build_app


def _client() -> TestClient:
    return TestClient(build_app(jobs_root=Path(tempfile.mkdtemp())))


def test_missing_video_returns_404():
    r = _client().get("/files/deadbeef/video.mp4")
    assert r.status_code == 404


def test_missing_cover_returns_404():
    r = _client().get("/files/deadbeef/cover.png")
    assert r.status_code == 404


def test_missing_srt_returns_404():
    r = _client().get("/files/deadbeef/video.srt")
    assert r.status_code == 404


def test_unknown_job_index_page_still_served():
    # sanity: the app itself builds and serves the form
    r = _client().get("/")
    assert r.status_code == 200


def _combined_output(result) -> str:
    return (result.output or "") + (result.stderr or "")


def test_unimplemented_provider_reports_clean_error(tmp_path):
    script = tmp_path / "s.md"
    script.write_text("# T\n\n正文内容。\n", encoding="utf-8")
    result = CliRunner().invoke(
        app, ["build", str(script), "-o", str(tmp_path / "out"), "--tts-provider", "doubao"]
    )
    assert result.exit_code == 2
    out = _combined_output(result)
    assert "error:" in out
    assert "not implemented" in out
    assert "Traceback" not in out


def test_unimplemented_provider_qwen_reports_clean_error(tmp_path):
    script = tmp_path / "s.md"
    script.write_text("# T\n\n正文内容。\n", encoding="utf-8")
    result = CliRunner().invoke(
        app, ["build", str(script), "-o", str(tmp_path / "out"), "--tts-provider", "qwen"]
    )
    assert result.exit_code == 2
    assert "Traceback" not in _combined_output(result)
