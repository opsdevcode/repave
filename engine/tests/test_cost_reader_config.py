from __future__ import annotations

from repave_engine.cost_actuals import (
    cost_reader_configured,
    resolve_cost_reader,
)
from repave_engine.settings import CostAwsConfig, CostAzureConfig


def test_resolve_cost_reader_explicit_aws() -> None:
    assert resolve_cost_reader(cost_reader="aws", cost_actuals_url="") == "aws"


def test_resolve_cost_reader_url_from_template() -> None:
    assert (
        resolve_cost_reader(cost_reader="", cost_actuals_url="https://cost.example/{name}") == "url"
    )


def test_cost_reader_configured_for_azure() -> None:
    assert cost_reader_configured(cost_reader="azure", cost_actuals_url="")


def test_portal_config_loads_cost_reader_blocks(tmp_path) -> None:
    from repave_engine.settings import load_portal_config

    (tmp_path / "repave.config.yaml").write_text(
        "\n".join(
            [
                "portal:",
                "  cost_reader: aws",
                "  cost_aws:",
                "    tag_key_owner: Team",
                "    tag_key_service: App",
            ]
        ),
        encoding="utf-8",
    )
    config = load_portal_config(tmp_path)
    assert config.cost_reader == "aws"
    assert config.cost_aws == CostAwsConfig(tag_key_owner="Team", tag_key_service="App")
    assert config.cost_azure == CostAzureConfig()
