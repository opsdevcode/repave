from __future__ import annotations

import json
from pathlib import Path

import pytest

from repave_engine.fleet import (
    FleetEntry,
    FleetError,
    normalize_repo_url,
    pins_from_repave_file,
    read_fleet,
    register_repo,
    unregister_repo,
)
from repave_engine.settings import load_fleet_config

PROVENANCE = """
apiVersion: repave.dev/v1beta1
kind: GoldenPathArtifact
spec:
  blueprint:
    name: terraform-module-generic
    version: 0.9.0
  standard:
    source: standards/terraform-standards
    version: 1.1.0
"""


def _entry(url: str = "https://github.com/acme/tf-vpc.git") -> FleetEntry:
    return FleetEntry(
        repo_url=url,
        blueprint_name="terraform-module-generic",
        blueprint_version="0.9.0",
        standard_source="standards/terraform-standards",
        standard_version="1.1.0",
        owner="platform",
        registered_by="tester",
    )


def test_register_then_read_returns_entry(tmp_path: Path) -> None:
    registry = tmp_path / "fleet" / "registry.jsonl"

    register_repo(registry, _entry())

    entries = read_fleet(registry)
    assert len(entries) == 1
    assert entries[0].repo_url == "https://github.com/acme/tf-vpc"
    assert entries[0].blueprint_version == "0.9.0"
    assert entries[0].registered_at, "registration timestamp should be stamped"


def test_repo_url_spellings_collapse_to_one_entry(tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"

    register_repo(registry, _entry("https://github.com/acme/tf-vpc.git"))
    register_repo(registry, _entry("https://github.com/acme/tf-vpc/"))

    assert len(read_fleet(registry)) == 1


def test_reregister_updates_pins_last_write_wins(tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    register_repo(registry, _entry())

    bumped = _entry()
    register_repo(registry, FleetEntry(**{**bumped.to_dict(), "blueprint_version": "1.0.0"}))

    entries = read_fleet(registry)
    assert len(entries) == 1
    assert entries[0].blueprint_version == "1.0.0"


def test_unregister_removes_entry_and_reports_unknown(tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    register_repo(registry, _entry())

    assert unregister_repo(registry, "https://github.com/acme/tf-vpc") is True
    assert read_fleet(registry) == ()
    assert unregister_repo(registry, "https://github.com/acme/tf-vpc") is False


def test_log_is_append_only(tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    register_repo(registry, _entry())
    unregister_repo(registry, "https://github.com/acme/tf-vpc")

    events = [json.loads(line) for line in registry.read_text().splitlines() if line.strip()]
    assert [event["event"] for event in events] == ["register", "unregister"]


def test_read_fleet_skips_corrupt_lines(tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    register_repo(registry, _entry())
    with registry.open("a", encoding="utf-8") as handle:
        handle.write("not json\n")
        handle.write(json.dumps({"event": "register"}) + "\n")  # no repo_url

    assert len(read_fleet(registry)) == 1


def test_read_fleet_missing_file_is_empty(tmp_path: Path) -> None:
    assert read_fleet(tmp_path / "absent.jsonl") == ()


def test_register_requires_blueprint_and_url(tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    with pytest.raises(FleetError):
        register_repo(registry, FleetEntry(repo_url="", blueprint_name="x", blueprint_version=""))
    with pytest.raises(FleetError):
        register_repo(
            registry,
            FleetEntry(repo_url="https://x/y", blueprint_name="", blueprint_version=""),
        )


def test_normalize_repo_url_rejects_blank() -> None:
    with pytest.raises(FleetError):
        normalize_repo_url("   ")


def test_pins_from_repave_file_reads_provenance(tmp_path: Path) -> None:
    (tmp_path / "repave.yaml").write_text(PROVENANCE, encoding="utf-8")

    pins = pins_from_repave_file(tmp_path)

    assert pins["blueprint_name"] == "terraform-module-generic"
    assert pins["standard_version"] == "1.1.0"


def test_pins_from_repave_file_requires_file_and_blueprint(tmp_path: Path) -> None:
    with pytest.raises(FleetError):
        pins_from_repave_file(tmp_path)

    (tmp_path / "repave.yaml").write_text("spec:\n  standard:\n    source: s\n", encoding="utf-8")
    with pytest.raises(FleetError):
        pins_from_repave_file(tmp_path)


def test_load_fleet_config_from_file_and_env(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "repave.config.yaml").write_text(
        "fleet:\n  file: fleet/custom.jsonl\n", encoding="utf-8"
    )

    config = load_fleet_config(tmp_path)
    assert config is not None
    assert config.enabled is True
    assert config.file == (tmp_path / "fleet" / "custom.jsonl").resolve()

    monkeypatch.setenv("REPAVE_FLEET_FILE", str(tmp_path / "override.jsonl"))
    overridden = load_fleet_config(tmp_path)
    assert overridden is not None
    assert overridden.file == tmp_path / "override.jsonl"


def test_load_fleet_config_absent_and_disabled(tmp_path: Path) -> None:
    assert load_fleet_config(tmp_path) is None

    (tmp_path / "repave.config.yaml").write_text("fleet:\n  enabled: false\n", encoding="utf-8")
    config = load_fleet_config(tmp_path)
    assert config is not None
    assert config.enabled is False
