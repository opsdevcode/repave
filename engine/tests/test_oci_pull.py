from __future__ import annotations

import json
from pathlib import Path

import pytest

from repave_engine.oci_pull import OciPullError, is_oci_pack_url, oci_reference, pull_oci_artifact


def test_is_oci_pack_url() -> None:
    assert is_oci_pack_url("oci://ghcr.io/acme/pack")
    assert is_oci_pack_url("OCI://ghcr.io/acme/pack")
    assert not is_oci_pack_url("https://github.com/acme/pack.git")


def test_oci_reference_tag_and_digest() -> None:
    assert (
        oci_reference("oci://ghcr.io/acme/org-blueprints", "v1.2.0")
        == "ghcr.io/acme/org-blueprints:v1.2.0"
    )
    assert (
        oci_reference("oci://ghcr.io/acme/org-blueprints/", "sha256:abcd")
        == "ghcr.io/acme/org-blueprints@sha256:abcd"
    )


def test_oci_reference_rejects_bad_url() -> None:
    with pytest.raises(OciPullError, match="oci://"):
        oci_reference("https://ghcr.io/acme/pack", "v1")
    with pytest.raises(OciPullError, match="registry"):
        oci_reference("oci://ghcr.io", "v1")


def test_pull_oci_artifact_invokes_oras(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "pack"
    captured: dict[str, object] = {}

    def fake_run(
        cmd: list[str],
        *,
        env: dict[str, str] | None = None,
        check: bool = False,
        **_kwargs: object,
    ) -> object:
        captured["cmd"] = cmd
        captured["env"] = env
        captured["check"] = check
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "blueprint.yaml").write_text("ok\n", encoding="utf-8")
        if env and "DOCKER_CONFIG" in env:
            config = Path(env["DOCKER_CONFIG"]) / "config.json"
            captured["docker_config"] = json.loads(config.read_text(encoding="utf-8"))
        return object()

    monkeypatch.setattr("repave_engine.oci_pull.run_subprocess", fake_run)

    pull_oci_artifact(
        "oci://ghcr.io/acme/org-blueprints",
        dest,
        ref="v1.2.0",
        token="ghp_secret",
    )

    assert captured["cmd"] == [
        "oras",
        "pull",
        "ghcr.io/acme/org-blueprints:v1.2.0",
        "--output",
        str(dest.resolve()),
    ]
    assert captured["check"] is True
    docker = captured["docker_config"]
    assert isinstance(docker, dict)
    assert "ghcr.io" in docker["auths"]
    assert (dest / "blueprint.yaml").read_text(encoding="utf-8") == "ok\n"


def test_pull_oci_artifact_names_missing_oras(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_run(*_args: object, **_kwargs: object) -> object:
        raise FileNotFoundError("oras")

    monkeypatch.setattr("repave_engine.oci_pull.run_subprocess", fake_run)

    with pytest.raises(OciPullError, match="oras executable not found"):
        pull_oci_artifact("oci://ghcr.io/acme/pack", tmp_path / "out", ref="v1")
