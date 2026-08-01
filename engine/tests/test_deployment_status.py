from __future__ import annotations

import httpx
import pytest

from repave_engine.deployment_status import (
    deployment_reader_configured,
    fetch_deployment_status_argocd,
    fetch_deployment_status_flux,
    fetch_deployment_status_url,
    fetch_entity_deployment_status_for_portal,
    format_deployment_template,
    parse_deployment_payload,
    resolve_deployment_reader,
)
from repave_engine.entity_catalog import CatalogEntity, ScorecardDimension
from repave_engine.settings import (
    DeploymentArgocdConfig,
    DeploymentFluxConfig,
    PortalConfig,
)


def _entity() -> CatalogEntity:
    return CatalogEntity(
        entity_id="acme-svc",
        display_name="acme-svc",
        repo_url=None,
        local_path=None,
        owner="platform",
        blueprint_name="app-service-generic",
        blueprint_version="1.0.0",
        standard_source="",
        standard_version="",
        component_type="service",
        lifecycle="production",
        operator_phase="",
        operator_message="",
        remediation_pr_url="",
        manifest_name="",
        manifest_namespace="",
        source="fleet",
        scorecard=(ScorecardDimension("pins", "Pins", "pass", ""),),
    )


def test_format_deployment_template_placeholders() -> None:
    url = format_deployment_template(
        "https://status.example/{name}?id={entity_id}&owner={owner}",
        _entity(),
    )
    assert url == "https://status.example/acme-svc?id=acme-svc&owner=platform"


def test_parse_deployment_payload() -> None:
    status = parse_deployment_payload(
        {
            "sync_status": "Synced",
            "health": "Healthy",
            "revision": "abc123def",
            "last_synced": "2026-08-01T12:00:00Z",
            "deep_link": "https://argocd.example/applications/acme-svc",
        },
        source="url",
    )
    assert status is not None
    assert status.sync_status == "synced"
    assert status.health == "healthy"
    assert status.revision == "abc123def"


def test_resolve_deployment_reader_from_url() -> None:
    assert (
        resolve_deployment_reader(
            deployment_reader="",
            deployment_status_url="https://status.example/{name}",
        )
        == "url"
    )


def test_deployment_reader_configured() -> None:
    assert deployment_reader_configured(deployment_reader="argocd", deployment_status_url="")
    assert not deployment_reader_configured(deployment_reader="", deployment_status_url="")


def test_fetch_url_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {
                "sync_status": "out_of_sync",
                "health": "degraded",
                "revision": "deadbeef",
                "last_synced": "2026-08-01T00:00:00Z",
            }

    monkeypatch.setattr(
        "repave_engine.deployment_status.httpx.get",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    status = fetch_deployment_status_url("https://status.example/{name}", _entity())
    assert status.sync_status == "out_of_sync"
    assert status.health == "degraded"
    assert status.source == "url"


def test_fetch_url_unreachable_returns_unknown(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*_args: object, **_kwargs: object) -> None:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr("repave_engine.deployment_status.httpx.get", _raise)
    status = fetch_deployment_status_url("https://status.example/{name}", _entity())
    assert status.sync_status == "unknown"
    assert status.health == "unknown"
    assert "unreachable" in status.detail.lower()


def test_fetch_argocd_parses_application(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "status": {
                    "sync": {"status": "Synced", "revision": "abc123"},
                    "health": {"status": "Healthy"},
                    "reconciledAt": "2026-08-01T10:00:00Z",
                }
            }

    monkeypatch.setattr(
        "repave_engine.deployment_status.httpx.get",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    status = fetch_deployment_status_argocd(
        base_url="https://argocd.example.com",
        application_template="{name}",
        entity=_entity(),
        token="test-token",
    )
    assert status.sync_status == "synced"
    assert status.health == "healthy"
    assert status.revision == "abc123"
    assert status.deep_link.endswith("/applications/acme-svc")


def test_fetch_flux_parses_kustomization(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, object]:
            return {
                "status": {
                    "conditions": [
                        {
                            "type": "Ready",
                            "status": "True",
                            "lastTransitionTime": "2026-08-01T11:00:00Z",
                        }
                    ],
                    "lastAppliedRevision": "main@sha1:abcdef",
                }
            }

    monkeypatch.setattr(
        "repave_engine.deployment_status.httpx.get",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    status = fetch_deployment_status_flux(
        api_server="https://k8s.example.com",
        namespace_template="apps",
        name_template="{name}",
        kind="kustomization",
        entity=_entity(),
        token="kube-token",
    )
    assert status.source == "flux"
    assert status.health == "healthy"
    assert status.revision == "main@sha1:abcdef"


def test_portal_dispatch_none_when_unconfigured() -> None:
    config = PortalConfig(density="default")
    assert fetch_entity_deployment_status_for_portal(config, _entity()) is None


def test_portal_dispatch_url(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, str]:
            return {"sync_status": "synced", "health": "healthy", "revision": "r1"}

    monkeypatch.setattr(
        "repave_engine.deployment_status.httpx.get",
        lambda *_args, **_kwargs: FakeResponse(),
    )
    config = PortalConfig(
        density="default",
        deployment_reader="url",
        deployment_status_url="https://status.example/{name}",
    )
    status = fetch_entity_deployment_status_for_portal(config, _entity())
    assert status is not None
    assert status.sync_status == "synced"


def test_portal_config_loads_deployment_blocks(tmp_path) -> None:
    from repave_engine.settings import load_portal_config

    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "portal:",
                "  deployment_reader: argocd",
                "  deployment_argocd:",
                "    base_url: https://argocd.example.com",
                "    application: 'env-{name}'",
                "  deployment_flux:",
                "    api_server: https://k8s.example.com",
                "    namespace: flux-system",
                "    kind: helmrelease",
            ]
        ),
        encoding="utf-8",
    )
    config = load_portal_config(tmp_path)
    assert config.deployment_reader == "argocd"
    assert config.deployment_argocd == DeploymentArgocdConfig(
        base_url="https://argocd.example.com",
        application="env-{name}",
    )
    assert config.deployment_flux == DeploymentFluxConfig(
        api_server="https://k8s.example.com",
        namespace="flux-system",
        name="{name}",
        kind="helmrelease",
    )
