"""Behavior tests for deploy/local/install-gate-toolchain.sh."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "deploy" / "local" / "install-gate-toolchain.sh"

# Every external command the installer shells out to, replaced by argv loggers.
STUBBED_COMMANDS = ("curl", "unzip", "tar", "install", "uv", "ansible-galaxy")

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")


def _run_installer(
    tmp_path: Path,
    *,
    curl_stub: str | None = None,
    galaxy_stub: str | None = None,
    **env_overrides: str,
) -> tuple[subprocess.CompletedProcess, str]:
    """Run the installer with stubbed downloaders; return the process and the argv log."""
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    log = tmp_path / "calls.log"
    for name in STUBBED_COMMANDS:
        stub = stub_dir / name
        if name == "curl" and curl_stub is not None:
            stub.write_text(curl_stub, encoding="utf-8")
        elif name == "ansible-galaxy" and galaxy_stub is not None:
            stub.write_text(galaxy_stub, encoding="utf-8")
        else:
            stub.write_text(
                f'#!/bin/sh\nprintf "{name} %s\\n" "$*" >> "$STUB_LOG"\nexit 0\n',
                encoding="utf-8",
            )
        stub.chmod(0o755)
    dest = tmp_path / "dest"
    dest.mkdir()

    env = {
        **os.environ,
        "PATH": f"{stub_dir}{os.pathsep}{os.environ['PATH']}",
        "STUB_LOG": str(log),
        "STUB_DIR": str(stub_dir),
        "REPO_ROOT": str(REPO_ROOT),
        "USE_UV_PIP": "1",
        "DEST": str(dest),
        **env_overrides,
    }
    proc = subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    calls = log.read_text(encoding="utf-8") if log.exists() else ""
    return proc, calls


def _lines(calls: str, command: str) -> list[str]:
    return [line for line in calls.splitlines() if line.startswith(f"{command} ")]


def test_default_run_verifies_tls_for_every_downloader(tmp_path: Path) -> None:
    proc, calls = _run_installer(tmp_path)

    assert proc.returncode == 0, proc.stderr
    curl_calls = _lines(calls, "curl")
    assert (
        len(curl_calls) == 8
    )  # terraform, tflint, conftest, infracost, helm, kubectl, actionlint, buf
    assert all("-fsSL" in call for call in curl_calls)
    assert all(" -o " in call for call in curl_calls)
    assert not any("--insecure" in call for call in curl_calls)
    galaxy_calls = _lines(calls, "ansible-galaxy")
    assert galaxy_calls
    assert all("--no-cache" in call for call in galaxy_calls)
    assert not any("--ignore-certs" in call for call in galaxy_calls)
    assert not any("--allow-insecure-host" in call for call in _lines(calls, "uv"))
    assert "WARNING" not in proc.stderr


def test_installer_download_urls_use_pins_file(tmp_path: Path) -> None:
    from repave_engine import ci_toolchain

    proc, calls = _run_installer(tmp_path)

    assert proc.returncode == 0, proc.stderr
    curl_blob = "\n".join(_lines(calls, "curl"))
    assert ci_toolchain.TERRAFORM_VERSION in curl_blob
    assert ci_toolchain.TFLINT_VERSION in curl_blob
    assert ci_toolchain.CONFTEST_VERSION in curl_blob
    assert ci_toolchain.HELM_VERSION in curl_blob
    assert ci_toolchain.INFRACOST_VERSION in curl_blob
    assert ci_toolchain.KUBECTL_VERSION in curl_blob
    assert ci_toolchain.ACTIONLINT_VERSION in curl_blob
    assert ci_toolchain.BUF_VERSION in curl_blob
    assert "bufbuild/buf" in curl_blob
    assert "rhysd/actionlint" in curl_blob
    assert "https://dl.k8s.io/" in curl_blob
    uv_blob = "\n".join(_lines(calls, "uv"))
    assert ci_toolchain.CHECKOV_PIP_SPEC in uv_blob


def test_insecure_opt_in_relaxes_curl_galaxy_and_uv(tmp_path: Path) -> None:
    proc, calls = _run_installer(tmp_path, REPAVE_TLS_INSECURE="1")

    assert proc.returncode == 0, proc.stderr
    curl_calls = _lines(calls, "curl")
    assert len(curl_calls) == 8
    assert all("--insecure" in call for call in curl_calls)
    assert all("--ignore-certs" in call for call in _lines(calls, "ansible-galaxy"))
    assert all("--allow-insecure-host" in call for call in _lines(calls, "uv"))
    assert "REPAVE_TLS_INSECURE=1" in proc.stderr


def test_collections_install_can_be_skipped(tmp_path: Path) -> None:
    proc, calls = _run_installer(tmp_path, INSTALL_ANSIBLE_COLLECTIONS="0")

    assert proc.returncode == 0, proc.stderr
    assert not _lines(calls, "ansible-galaxy")
    assert _lines(calls, "uv")  # ansible-lint/yamllint still installed


def test_kubectl_install_can_be_skipped(tmp_path: Path) -> None:
    proc, calls = _run_installer(tmp_path, INSTALL_KUBECTL="0")

    assert proc.returncode == 0, proc.stderr
    curl_blob = "\n".join(_lines(calls, "curl"))
    assert "dl.k8s.io" not in curl_blob
    assert len(_lines(calls, "curl")) == 7  # without kubectl; actionlint and buf still install


def test_buf_install_can_be_skipped(tmp_path: Path) -> None:
    proc, calls = _run_installer(tmp_path, INSTALL_BUF="0")

    assert proc.returncode == 0, proc.stderr
    curl_blob = "\n".join(_lines(calls, "curl"))
    assert "bufbuild/buf" not in curl_blob


def test_curl_download_retries_transient_http_errors(tmp_path: Path) -> None:
    proc, calls = _run_installer(
        tmp_path,
        curl_stub=(
            "#!/bin/sh\n"
            'count_file="$STUB_DIR/curl-count"\n'
            "n=0\n"
            'if [ -f "$count_file" ]; then n=$(cat "$count_file"); fi\n'
            "n=$((n + 1))\n"
            'echo "$n" > "$count_file"\n'
            'printf "curl %s\\n" "$*" >> "$STUB_LOG"\n'
            'if [ "$n" -le 2 ]; then exit 22; fi\n'
            "exit 0\n"
        ),
        DOWNLOAD_RETRY_DELAY="0",
    )

    assert proc.returncode == 0, proc.stderr
    assert len(_lines(calls, "curl")) == 10  # 2 failures + 8 successful downloads
    assert "retrying in 0s" in proc.stderr


def test_galaxy_install_retries_transient_errors(tmp_path: Path) -> None:
    proc, calls = _run_installer(
        tmp_path,
        galaxy_stub=(
            "#!/bin/sh\n"
            'count_file="$STUB_DIR/galaxy-count"\n'
            "n=0\n"
            'if [ -f "$count_file" ]; then n=$(cat "$count_file"); fi\n'
            "n=$((n + 1))\n"
            'echo "$n" > "$count_file"\n'
            'printf "ansible-galaxy %s\\n" "$*" >> "$STUB_LOG"\n'
            'if [ "$n" -le 2 ]; then exit 1; fi\n'
            "exit 0\n"
        ),
        DOWNLOAD_RETRY_DELAY="0",
    )

    assert proc.returncode == 0, proc.stderr
    assert len(_lines(calls, "ansible-galaxy")) == 3
    assert "retrying in 0s" in proc.stderr


def test_galaxy_install_gives_up_after_attempts(tmp_path: Path) -> None:
    proc, calls = _run_installer(
        tmp_path,
        galaxy_stub=('#!/bin/sh\nprintf "ansible-galaxy %s\\n" "$*" >> "$STUB_LOG"\nexit 1\n'),
        DOWNLOAD_RETRY_DELAY="0",
        DOWNLOAD_RETRY_ATTEMPTS="3",
    )

    assert proc.returncode == 1
    assert len(_lines(calls, "ansible-galaxy")) == 3
    assert "ansible-galaxy failed after 3 attempts" in proc.stderr


def test_curl_download_gives_up_after_attempts(tmp_path: Path) -> None:
    proc, calls = _run_installer(
        tmp_path,
        curl_stub=('#!/bin/sh\nprintf "curl %s\\n" "$*" >> "$STUB_LOG"\nexit 22\n'),
        DOWNLOAD_RETRY_DELAY="0",
        DOWNLOAD_RETRY_ATTEMPTS="3",
    )

    assert proc.returncode == 22
    assert len(_lines(calls, "curl")) == 3
    assert "download failed after 3 attempts" in proc.stderr


def test_script_is_syntactically_valid() -> None:
    proc = subprocess.run(["bash", "-n", str(SCRIPT)], capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr


def test_script_uses_lf_line_endings() -> None:
    """CRLF breaks the shebang inside the container; .gitattributes pins eol=lf."""
    assert b"\r\n" not in SCRIPT.read_bytes()
