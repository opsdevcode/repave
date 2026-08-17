"""Pull an OCI blueprint pack into a local cache directory (oras)."""

from __future__ import annotations

import base64
import json
import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from repave_engine.subprocess_run import run_subprocess

logger = logging.getLogger(__name__)

_OCI_PREFIX = "oci://"


class OciPullError(RuntimeError):
    """Failed to pull an OCI artifact."""


def is_oci_pack_url(url: str) -> bool:
    return url.strip().lower().startswith(_OCI_PREFIX)


def oci_reference(url: str, ref: str) -> str:
    """Turn oci://host/path + tag-or-digest into an oras reference."""
    raw = url.strip()
    if not is_oci_pack_url(raw):
        raise OciPullError(
            f"OCI pack URL must start with oci:// (got {url!r}; set blueprint_packs.sources[].url)"
        )
    host_path = raw[len(_OCI_PREFIX) :].strip().rstrip("/")
    if not host_path or "/" not in host_path:
        raise OciPullError(
            f"OCI pack URL {url!r} must be oci://<registry>/<repository> "
            "(set blueprint_packs.sources[].url)"
        )
    pin = ref.strip()
    if not pin:
        raise OciPullError(
            "OCI pack ref is required (tag or sha256:digest; set blueprint_packs.sources[].ref)"
        )
    if pin.startswith("sha256:"):
        return f"{host_path}@{pin}"
    return f"{host_path}:{pin}"


def _registry_host(url: str) -> str:
    host_path = url.strip()[len(_OCI_PREFIX) :].strip()
    return host_path.split("/", 1)[0]


def _docker_config_with_token(host: str, token: str) -> dict[str, object]:
    userinfo = f"x-access-token:{token}"
    auth = base64.b64encode(userinfo.encode()).decode("ascii")
    return {"auths": {host: {"auth": auth}}}


def pull_oci_artifact(
    url: str,
    dest_dir: Path,
    *,
    ref: str,
    token: str | None = None,
) -> None:
    """Pull url@ref into dest_dir with oras. Token is optional (public or docker login)."""
    reference = oci_reference(url, ref)
    dest_dir = dest_dir.resolve()
    dest_dir.parent.mkdir(parents=True, exist_ok=True)
    if dest_dir.exists():
        shutil.rmtree(dest_dir)
    dest_dir.mkdir(parents=True)

    cmd = ["oras", "pull", reference, "--output", str(dest_dir)]
    env = os.environ.copy()
    config_dir: tempfile.TemporaryDirectory[str] | None = None
    secret = (token or "").strip() or None
    if secret:
        config_dir = tempfile.TemporaryDirectory(prefix="repave-oras-")
        config_path = Path(config_dir.name)
        (config_path / "config.json").write_text(
            json.dumps(_docker_config_with_token(_registry_host(url), secret)),
            encoding="utf-8",
        )
        env["DOCKER_CONFIG"] = str(config_path)

    try:
        run_subprocess(cmd, env=env, check=True)
    except FileNotFoundError as exc:
        raise OciPullError(
            "oras executable not found — install oras "
            "(https://oras.land) or use a git blueprint_packs url"
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        if secret:
            detail = detail.replace(secret, "***")
        raise OciPullError(detail or f"oras pull failed for {reference}") from exc
    finally:
        if config_dir is not None:
            config_dir.cleanup()

    if not any(dest_dir.iterdir()):
        raise OciPullError(
            f"oras pull {reference} wrote no files — "
            "the artifact must contain a blueprint catalog (or set subdir)"
        )
