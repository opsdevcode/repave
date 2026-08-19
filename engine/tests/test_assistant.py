"""Tests for governed assistant intent → golden-path matching."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from helpers import make_blueprint
from repave_engine.api import create_app
from repave_engine.assistant import is_assistant_enabled, resolve_intent
from repave_engine.blueprint import InputField
from repave_engine.v3_foundation import load_v3_foundation_config


def _write_min_config(root: Path, *, extra: str = "") -> None:
    (root / "repave.config.yaml").write_text(
        f"apiVersion: repave.dev/v1\noutput:\n  github_org: acme\n  modules_root: ../mods\n{extra}",
        encoding="utf-8",
    )


def test_assistant_disabled_by_default(tmp_path: Path) -> None:
    _write_min_config(tmp_path)
    assert is_assistant_enabled(tmp_path) is False
    assert load_v3_foundation_config(tmp_path).assistant_enabled is False


def test_assistant_requires_v3_enabled(tmp_path: Path) -> None:
    _write_min_config(
        tmp_path,
        extra="v3:\n  enabled: false\n  assistant:\n    enabled: true\n",
    )
    with pytest.raises(ValueError, match=r"v3\.assistant\.enabled"):
        load_v3_foundation_config(tmp_path)


def test_assistant_opt_in(tmp_path: Path) -> None:
    _write_min_config(
        tmp_path,
        extra="v3:\n  enabled: true\n  assistant:\n    enabled: true\n",
    )
    assert is_assistant_enabled(tmp_path) is True


def test_resolve_intent_empty() -> None:
    result = resolve_intent("   ", blueprints=())
    assert result.matches == ()
    assert "short description" in result.message


def test_resolve_intent_ranks_terraform_module(tmp_path: Path) -> None:
    terraform = make_blueprint(
        tmp_path,
        name="terraform-module-generic",
        artifact_type="terraform-module",
        inputs=(
            InputField(name="module_name", type="string", required=True),
            InputField(
                name="cloud_provider",
                type="string",
                required=True,
                enum=("aws", "azure", "gcp"),
            ),
        ),
    )
    opa = make_blueprint(
        tmp_path / "opa",
        name="opa-policy-generic",
        artifact_type="opa-policy",
        inputs=(),
    )
    result = resolve_intent(
        "generate a terraform module named vpc-core for aws",
        blueprints=(terraform, opa),
    )
    assert result.matches
    assert result.matches[0].blueprint == "terraform-module-generic"
    assert result.matches[0].citations[0].source == "catalog:terraform-module-generic"
    assert result.matches[0].suggested_inputs["cloud_provider"] == "aws"
    assert result.matches[0].suggested_inputs["module_name"] == "vpc-core"
    assert result.tools == ("catalog.blueprints",)


def test_resolve_intent_no_match(tmp_path: Path) -> None:
    blueprint = make_blueprint(tmp_path, name="helm-chart-generic", artifact_type="helm-chart")
    result = resolve_intent("completely unrelated xyzzy", blueprints=(blueprint,))
    assert result.matches == ()
    assert "No golden path matched" in result.message


def test_assistant_page_404_when_off(repo_root: Path, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/assistant")
    assert response.status_code == 404


def test_assistant_html_and_api_when_on(
    repo_root: Path, output_config, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("repave_engine.api.is_assistant_enabled", lambda _root: True)
    monkeypatch.setattr("repave_engine.api_v2.router.is_assistant_enabled", lambda _root: True)
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    page = client.get("/assistant")
    assert page.status_code == 200
    assert "Describe the golden path" in page.text
    posted = client.post("/assistant", data={"intent": "terraform module for aws"})
    assert posted.status_code == 200
    assert "terraform-module-generic" in posted.text
    assert "catalog:terraform-module-generic" in posted.text
    api = client.post(
        "/api/v2/assistant/resolve",
        json={"intent": "terraform module named networking-vnet for azure"},
    )
    assert api.status_code == 200
    body = api.json()
    assert body["matches"][0]["blueprint"] == "terraform-module-generic"
    assert body["matches"][0]["suggested_inputs"]["cloud_provider"] == "azure"
    assert body["matches"][0]["suggested_inputs"]["module_name"] == "networking-vnet"


def test_api_v2_assistant_404_when_off(repo_root: Path, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post("/api/v2/assistant/resolve", json={"intent": "terraform module"})
    assert response.status_code == 404
    assert "v3.assistant.enabled" in response.json()["detail"]
