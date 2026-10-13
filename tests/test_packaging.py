"""Packaging / CI contract tests — the release must actually ship its assets.

v0.3.0: the release workflow built dist/ but only pushed a CI artifact, so the
GitHub Release published with zero downloadable assets. These pins keep the
attach-to-release step and the serve form dependency from regressing.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_release_workflow_attaches_assets_to_the_release():
    text = (REPO_ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    # assets must reach the GitHub Release, not just the CI artifact store
    assert "gh release upload" in text
    assert "--clobber" in text  # idempotent re-runs overwrite same-named assets
    # the step authenticates (github.token via GH_TOKEN) so it can write releases
    assert "github.token" in text


def test_python_multipart_is_a_declared_dependency():
    pyproject = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    deps = pyproject["project"]["dependencies"]
    # `zhicast serve` hard-requires python-multipart at app-build time; without
    # this pin a plain `pip install zhicast` yields a serve command that crashes.
    assert any(d.split(">")[0].strip() == "python-multipart" for d in deps)
