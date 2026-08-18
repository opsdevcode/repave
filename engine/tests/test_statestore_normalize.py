from __future__ import annotations

from typing import Any

from repave_engine.statestore.normalize import (
    REDACTED,
    edges_from_plan_json,
    instance_address,
    is_sensitive_name,
    normalize_state,
    redact_attributes,
    resource_address,
    sensitive_attributes_from_provider_schema,
    strip_index,
)
from repave_engine.statestore.state_document import parse_state_document
from statestore_support import make_state, managed_resource


def _normalize(resources: list[dict[str, Any]], **kwargs: Any):
    return normalize_state(parse_state_document(make_state(resources=resources)), **kwargs)


def test_resource_address_includes_module_and_data_prefix() -> None:
    assert resource_address({"type": "aws_vpc", "name": "main"}) == "aws_vpc.main"
    assert (
        resource_address({"module": "module.net", "type": "aws_vpc", "name": "main"})
        == "module.net.aws_vpc.main"
    )
    assert (
        resource_address({"mode": "data", "type": "aws_ami", "name": "base"}) == "data.aws_ami.base"
    )


def test_instance_address_quotes_string_keys_only() -> None:
    assert instance_address("aws_instance.web", None) == "aws_instance.web"
    assert instance_address("aws_instance.web", 0) == "aws_instance.web[0]"
    assert instance_address("aws_instance.web", "blue") == 'aws_instance.web["blue"]'


def test_strip_index_removes_for_each_and_count_suffixes() -> None:
    assert strip_index("aws_instance.web[0]") == "aws_instance.web"
    assert strip_index('aws_instance.web["blue"]') == "aws_instance.web"
    assert strip_index("aws_instance.web") == "aws_instance.web"
    assert strip_index("module.x.aws_instance.web[count.index]") == "module.x.aws_instance.web"


def test_is_sensitive_name_matches_case_insensitively() -> None:
    assert is_sensitive_name("Password")
    assert is_sensitive_name("db_master_secret")
    assert not is_sensitive_name("instance_type")


def test_redact_attributes_covers_all_three_sources() -> None:
    attributes = {
        "id": "i-123",
        "password": "hunter2",
        "declared": "from-terraform",
        "from_schema": "provider-marked",
    }
    cleaned, redacted = redact_attributes(
        attributes,
        declared_sensitive={"declared"},
        schema_sensitive={"from_schema"},
    )
    assert cleaned["id"] == "i-123"
    assert cleaned["password"] == REDACTED
    assert cleaned["declared"] == REDACTED
    assert cleaned["from_schema"] == REDACTED
    assert redacted == ("declared", "from_schema", "password")


def test_normalize_builds_resources_and_depends_on_edges() -> None:
    result = _normalize(
        [
            managed_resource("aws_vpc", "main"),
            managed_resource("aws_subnet", "web", depends_on=["aws_vpc.main"]),
        ]
    )
    assert result.addresses == {"aws_vpc.main", "aws_subnet.web"}
    assert [(e.from_address, e.to_address, e.kind) for e in result.edges] == [
        ("aws_subnet.web", "aws_vpc.main", "depends_on")
    ]


def test_normalize_drops_self_edges_and_index_suffixes() -> None:
    result = _normalize(
        [
            managed_resource("aws_vpc", "main"),
            managed_resource(
                "aws_subnet",
                "web",
                depends_on=["aws_vpc.main[0]", "aws_subnet.web"],
            ),
        ]
    )
    assert [(e.from_address, e.to_address) for e in result.edges] == [
        ("aws_subnet.web", "aws_vpc.main")
    ]


def test_normalize_redacts_instance_declared_sensitive_attributes() -> None:
    resource = managed_resource("aws_db_instance", "db", attributes={"id": "db-1", "creds": "x"})
    resource["instances"][0]["sensitive_attributes"] = [[{"type": "get_attr", "value": "creds"}]]
    result = _normalize([resource])

    instance = result.resources[0].instances[0]
    assert instance.attributes == {"id": "db-1", "creds": REDACTED}
    assert instance.redacted_keys == ("creds",)


def test_normalize_applies_provider_schema_sensitivity_by_type() -> None:
    result = _normalize(
        [managed_resource("aws_db_instance", "db", attributes={"id": "db-1", "endpoint": "e"})],
        schema_sensitive={"aws_db_instance": {"endpoint"}},
    )
    assert result.resources[0].instances[0].attributes["endpoint"] == REDACTED


def test_normalize_records_index_key_and_counts_instances() -> None:
    resource = managed_resource("aws_instance", "web", index_key=0)
    resource["instances"].append({"schema_version": 0, "index_key": 1, "attributes": {"id": "i-2"}})
    result = _normalize([resource])

    addresses = [i.address for i in result.resources[0].instances]
    assert addresses == ["aws_instance.web[0]", "aws_instance.web[1]"]


def test_normalize_marks_data_sources() -> None:
    resource = managed_resource("aws_ami", "base")
    resource["mode"] = "data"
    result = _normalize([resource])
    assert result.resources[0].is_data_source


def test_edges_from_plan_json_reads_configuration_references() -> None:
    payload = {
        "configuration": {
            "root_module": {
                "resources": [
                    {
                        "address": "aws_subnet.web",
                        "expressions": {
                            "vpc_id": {"references": ["aws_vpc.main.id", "aws_vpc.main"]},
                            "tags": {"nested": {"references": ["var.env"]}},
                        },
                    }
                ]
            }
        }
    }
    edges = edges_from_plan_json(payload)
    assert [(e.from_address, e.to_address, e.kind) for e in edges] == [
        ("aws_subnet.web", "aws_vpc.main", "reference")
    ]


def test_edges_from_plan_json_prefixes_module_calls() -> None:
    payload = {
        "configuration": {
            "root_module": {
                "module_calls": {
                    "net": {
                        "module": {
                            "resources": [
                                {
                                    "address": "aws_subnet.web",
                                    "expressions": {"vpc_id": {"references": ["aws_vpc.main"]}},
                                }
                            ]
                        }
                    }
                }
            }
        }
    }
    edges = edges_from_plan_json(payload)
    assert [(e.from_address, e.to_address) for e in edges] == [
        ("module.net.aws_subnet.web", "module.net.aws_vpc.main")
    ]


def test_edges_from_plan_json_tolerates_garbage() -> None:
    assert edges_from_plan_json(None) == []
    assert edges_from_plan_json({"configuration": "not-a-dict"}) == []


def test_sensitive_attributes_from_provider_schema() -> None:
    payload = {
        "provider_schemas": {
            "registry.terraform.io/hashicorp/aws": {
                "resource_schemas": {
                    "aws_db_instance": {
                        "block": {
                            "attributes": {
                                "password": {"sensitive": True},
                                "identifier": {"sensitive": False},
                            }
                        }
                    }
                },
                "data_source_schemas": {
                    "aws_secret": {"block": {"attributes": {"value": {"sensitive": True}}}}
                },
            }
        }
    }
    assert sensitive_attributes_from_provider_schema(payload) == {
        "aws_db_instance": {"password"},
        "aws_secret": {"value"},
    }


def test_sensitive_attributes_from_provider_schema_tolerates_garbage() -> None:
    assert sensitive_attributes_from_provider_schema({"provider_schemas": []}) == {}
