from __future__ import annotations

from pathlib import Path

import yaml

from repave_engine.observability_catalog import load_observability_catalog
from repave_engine.service_inventory import (
    list_inventory_services,
    load_merged_observability_catalog,
    merge_catalog_services,
    services_inventory_json,
)


def _write_obs_repo(modules_root: Path, repo_name: str, service_name: str) -> None:
    repo = modules_root / repo_name
    repo.mkdir(parents=True)
    spec = {
        "artifactType": "observability",
        "observability": {
            "service_name": service_name,
            "organization": "payments",
            "team": "payments-core",
            "backend": "grafana",
            "output_mode": "native",
            "runbook_url": "https://runbooks.example/payments",
        },
    }
    (repo / "repave.yaml").write_text(
        yaml.safe_dump({"spec": spec}, sort_keys=False),
        encoding="utf-8",
    )


def test_list_inventory_services_skips_non_observability(tmp_path: Path) -> None:
    modules_root = tmp_path / "modules"
    modules_root.mkdir()
    _write_obs_repo(modules_root, "observability-payments-checkout", "checkout")
    (modules_root / "tf-aws-vpc").mkdir()
    (modules_root / "tf-aws-vpc" / "repave.yaml").write_text(
        yaml.safe_dump({"spec": {"artifactType": "terraform-module"}}),
        encoding="utf-8",
    )
    found = list_inventory_services(modules_root)
    assert len(found) == 1
    assert found[0].id == "checkout"
    assert found[0].repo_name == "observability-payments-checkout"


def test_merge_catalog_services_catalog_wins(repo_root: Path, tmp_path: Path) -> None:
    catalog = load_observability_catalog(repo_root)
    modules_root = tmp_path / "modules"
    modules_root.mkdir()
    first_catalog_id = catalog.services[0].id
    _write_obs_repo(
        modules_root,
        f"observability-platform-{first_catalog_id}",
        first_catalog_id,
    )
    _write_obs_repo(modules_root, "dashboards-platform-new-svc", "new-svc")
    discovered = list_inventory_services(modules_root)
    merged = merge_catalog_services(catalog, discovered)
    merged_ids = {svc.id for svc in merged}
    assert "new-svc" in merged_ids
    catalog_svc = next(s for s in merged if s.id == first_catalog_id)
    assert (
        catalog_svc.description
        == next(s for s in catalog.services if s.id == first_catalog_id).description
    )


def test_services_inventory_json_and_merged_load(repo_root: Path, tmp_path: Path) -> None:
    modules_root = tmp_path / "modules"
    modules_root.mkdir()
    _write_obs_repo(modules_root, "observability-platform-edge-api", "edge-api")
    catalog = load_observability_catalog(repo_root)
    payload = services_inventory_json(modules_root, catalog, merge=True)
    assert payload["discovered_count"] == 1
    ids = {item["id"] for item in payload["services"]}
    assert "edge-api" in ids
    edge = next(item for item in payload["services"] if item["id"] == "edge-api")
    assert edge["source_kind"] == "discovered"

    merged, catalog_ids = load_merged_observability_catalog(repo_root, modules_root)
    assert "edge-api" in {svc.id for svc in merged.services}
    assert isinstance(catalog_ids, frozenset)
