"""Tests for governed assistant intent → golden-path matching."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from helpers import make_blueprint
from repave_engine.api import create_app
from repave_engine.assistant import is_assistant_enabled, resolve_catalog_intent, resolve_intent
from repave_engine.assistant_corpus import corpus_allowed, load_assistant_corpus, search_corpus
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
    assert load_v3_foundation_config(tmp_path).assistant_retrieval == "memory"


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
    assert "cloud_provider=aws" in result.matches[0].form_href
    assert "module_name=vpc-core" in result.matches[0].form_href
    assert "corpus.standards" in result.tools


def test_resolve_intent_no_match(tmp_path: Path) -> None:
    blueprint = make_blueprint(tmp_path, name="helm-chart-generic", artifact_type="helm-chart")
    result = resolve_intent("completely unrelated xyzzy", blueprints=(blueprint,))
    assert result.matches == ()
    assert "No golden path matched" in result.message


def test_assistant_page_404_when_off(repo_root: Path, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.get("/assistant")
    assert response.status_code == 404


def test_corpus_denied_when_auth_role_cannot_view() -> None:
    assert corpus_allowed(role=None, auth_enabled=True) is False
    assert corpus_allowed(role="unknown", auth_enabled=True) is False
    assert corpus_allowed(role="viewer", auth_enabled=True) is True
    assert corpus_allowed(role=None, auth_enabled=False) is True


def test_load_corpus_stays_in_allowed_roots(repo_root: Path) -> None:
    documents = load_assistant_corpus(repo_root)
    sources = {item.source for item in documents}
    assert any(item.startswith("standards/") for item in sources)
    assert any(item.startswith("policy/") for item in sources)
    assert not any(item.startswith("docs/") for item in sources)
    assert not any(item.startswith("engine/") for item in sources)
    hits = search_corpus(documents, tokens=frozenset({"terraform", "module", "layout"}))
    assert hits
    assert hits[0].source.startswith("standards/")


def test_resolve_catalog_intent_cites_standards(repo_root: Path) -> None:
    result = resolve_catalog_intent(
        repo_root,
        intent="terraform module layout standard",
        auth_enabled=False,
    )
    sources = {item.source for item in result.citations}
    assert any(source.startswith("standards/") for source in sources)
    assert result.matches
    assert result.matches[0].citations[0].source.startswith("catalog:")


def test_resolve_catalog_intent_skips_corpus_when_role_denied(repo_root: Path) -> None:
    result = resolve_catalog_intent(
        repo_root,
        intent="terraform module layout standard",
        role=None,
        auth_enabled=True,
    )
    assert result.citations == ()
    assert result.matches


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
    assert "cloud_provider=aws" in posted.text
    assert "standards/" in posted.text or "policy/" in posted.text
    api = client.post(
        "/api/v2/assistant/resolve",
        json={"intent": "terraform module named networking-vnet for azure"},
    )
    assert api.status_code == 200
    body = api.json()
    assert body["matches"][0]["blueprint"] == "terraform-module-generic"
    assert body["matches"][0]["suggested_inputs"]["cloud_provider"] == "azure"
    assert body["matches"][0]["suggested_inputs"]["module_name"] == "networking-vnet"
    assert "cloud_provider=azure" in body["matches"][0]["form_href"]
    assert "module_name=networking-vnet" in body["matches"][0]["form_href"]
    assert body["citations"]
    assert body["citations"][0]["source"]
    assert not str(body["citations"][0]["source"]).startswith("docs/")


def test_api_v2_assistant_404_when_off(repo_root: Path, output_config) -> None:
    client = TestClient(create_app(repo_root=repo_root, output_config=output_config))
    response = client.post("/api/v2/assistant/resolve", json={"intent": "terraform module"})
    assert response.status_code == 404
    assert "v3.assistant.enabled" in response.json()["detail"]
