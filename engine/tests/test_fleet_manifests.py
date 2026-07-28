from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from repave_engine.cli import build_parser, cmd_fleet_manifests
from repave_engine.fleet import FleetEntry, FleetError, register_repo
from repave_engine.fleet_manifests import manifest_for, render_manifests, resource_name


def _entry(url: str = "https://github.com/acme/tf-vpc", **overrides: str) -> FleetEntry:
    fields = {
        "repo_url": url,
        "blueprint_name": "terraform-module-generic",
        "blueprint_version": "0.9.0",
        "standard_source": "standards/terraform-standards",
        "standard_version": "1.1.0",
        "owner": "platform",
        "registered_by": "tester",
    }
    fields.update(overrides)
    return FleetEntry(**fields)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://github.com/acme/tf-vpc", "acme-tf-vpc"),
        ("https://github.com/acme/tf-vpc.git", "acme-tf-vpc"),
        ("git@github.com:acme/tf-vpc.git", "acme-tf-vpc"),
        ("ssh://git@ghe.corp.example.com/acme/Tf_VPC", "acme-tf-vpc"),
        ("https://gitlab.com/group/sub/tf-vpc", "sub-tf-vpc"),
    ],
)
def test_resource_name_is_stable_across_url_spellings(url: str, expected: str) -> None:
    assert resource_name(url) == expected


def test_resource_name_includes_owner_to_avoid_collisions() -> None:
    assert resource_name("https://github.com/acme/vpc") != resource_name(
        "https://github.com/other/vpc"
    )


def test_resource_name_rejects_unusable_url() -> None:
    with pytest.raises(FleetError):
        resource_name("https://")


def test_manifest_matches_crd_shape() -> None:
    body = manifest_for(_entry())

    assert body["apiVersion"] == "repave.dev/v1alpha1"
    assert body["kind"] == "GoldenPathRepo"
    assert body["metadata"]["name"] == "acme-tf-vpc"
    assert body["metadata"]["namespace"] == "default"
    assert body["metadata"]["labels"] == {"repave.dev/managed-by": "repave-fleet"}
    assert body["metadata"]["annotations"] == {"repave.dev/owner": "platform"}
    assert body["spec"]["repoURL"] == "https://github.com/acme/tf-vpc"
    assert body["spec"]["desiredPins"] == {
        "blueprintName": "terraform-module-generic",
        "blueprintVersion": "0.9.0",
        "standardSource": "standards/terraform-standards",
        "standardVersion": "1.1.0",
    }


def test_manifest_omits_owner_annotation_when_absent() -> None:
    assert "annotations" not in manifest_for(_entry(owner=""))["metadata"]


def test_manifest_uses_repo_url_not_local_path() -> None:
    # The operator clones repoURL; a registry entry is always remote.
    assert "localPath" not in manifest_for(_entry())["spec"]


@pytest.mark.parametrize(
    "missing",
    ["blueprint_version", "standard_source", "standard_version"],
)
def test_manifest_requires_full_desired_pins(missing: str) -> None:
    # desiredPins fields are MinLength=1 in the CRD, so a partial entry must fail loudly.
    with pytest.raises(FleetError, match=missing):
        manifest_for(_entry(**{missing: ""}))


def test_render_writes_one_file_per_repo(tmp_path: Path) -> None:
    entries = [_entry(), _entry("https://github.com/acme/ansible-baseline")]

    rendered = render_manifests(entries, tmp_path / "manifests")

    assert [item.name for item in rendered] == ["acme-tf-vpc", "acme-ansible-baseline"]
    for item in rendered:
        assert item.path.is_file()
        body = yaml.safe_load(item.path.read_text())
        assert body["spec"]["repoURL"] == item.entry.repo_url


def test_render_is_deterministic(tmp_path: Path) -> None:
    out = tmp_path / "manifests"
    entries = [_entry()]

    render_manifests(entries, out)
    first = (out / "acme-tf-vpc.yaml").read_text()
    render_manifests(entries, out)

    assert (out / "acme-tf-vpc.yaml").read_text() == first


def test_render_rejects_colliding_names(tmp_path: Path) -> None:
    entries = [_entry("https://github.com/acme/tf-vpc"), _entry("https://gitlab.com/acme/tf-vpc")]

    with pytest.raises(FleetError, match="both map to resource name"):
        render_manifests(entries, tmp_path / "manifests")


def test_render_writes_nothing_when_a_manifest_is_invalid(tmp_path: Path) -> None:
    out = tmp_path / "manifests"
    entries = [_entry(), _entry("https://github.com/acme/broken", standard_version="")]

    with pytest.raises(FleetError):
        render_manifests(entries, out)

    # Validation happens before any write, so a bad entry cannot leave a partial apply set.
    assert not out.exists() or list(out.iterdir()) == []


def test_render_honors_namespace(tmp_path: Path) -> None:
    rendered = render_manifests([_entry()], tmp_path / "m", namespace="repave-system")

    body = yaml.safe_load(rendered[0].path.read_text())
    assert body["metadata"]["namespace"] == "repave-system"


CONTRACT_ENTRIES = (
    _entry(
        "https://github.com/acme/tf-vpc",
        registered_by="eric@example.com",
    ),
    _entry(
        "https://github.com/acme/opa-guardrails",
        blueprint_name="opa-policy-generic",
        blueprint_version="1.0",
        standard_source="standards/policy/opa.md",
        standard_version="1.2.0",
        owner="",
        registered_by="eric@example.com",
    ),
)


def test_checked_in_operator_fixtures_match_renderer(repo_root: Path, tmp_path: Path) -> None:
    """The operator decodes these fixtures strictly, so they must equal current output.

    See operator/internal/controller/fleet_manifest_test.go. If this fails, the renderer
    changed and the fixtures need regenerating — otherwise the Go test is validating a
    manifest shape the engine no longer produces.
    """
    fixture_dir = repo_root / "operator" / "testdata" / "fleet"
    rendered = render_manifests(list(CONTRACT_ENTRIES), tmp_path / "out")

    for item in rendered:
        fixture = fixture_dir / item.path.name
        assert fixture.is_file(), f"missing operator fixture {fixture}"
        assert fixture.read_text(encoding="utf-8") == item.path.read_text(encoding="utf-8"), (
            f"{fixture.name} is stale; regenerate the operator fleet fixtures"
        )


def _args(**kwargs: object):
    defaults = {"repo_root": ".", "namespace": "default"}
    defaults.update(kwargs)
    return type("Args", (), defaults)()


def test_cli_renders_manifests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    registry = tmp_path / "registry.jsonl"
    monkeypatch.setenv("REPAVE_FLEET_FILE", str(registry))
    register_repo(registry, _entry())
    out = tmp_path / "manifests"

    assert cmd_fleet_manifests(_args(output=str(out))) == 0

    output = capsys.readouterr().out
    assert "Rendered 1 GoldenPathRepo manifest(s)" in output
    assert "kubectl apply -f" in output
    assert (out / "acme-tf-vpc.yaml").is_file()


def test_cli_empty_registry_renders_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    monkeypatch.setenv("REPAVE_FLEET_FILE", str(tmp_path / "registry.jsonl"))
    out = tmp_path / "manifests"

    assert cmd_fleet_manifests(_args(output=str(out))) == 0

    assert "nothing to render" in capsys.readouterr().out
    assert not out.exists()


def test_parser_exposes_fleet_manifests() -> None:
    args = build_parser().parse_args(["fleet-manifests", "--output", "/tmp/x"])

    assert args.func is cmd_fleet_manifests
    assert args.namespace == "default"
