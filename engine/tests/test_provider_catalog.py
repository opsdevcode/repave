from __future__ import annotations

import json

import pytest

from repave_engine.provider_catalog import normalize_provider_service_scope

SAMPLE_CATALOG = {
    "aws": {
        "s3": {
            "resources": ["bucket", "bucket_acl", "bucket_policy", "object"],
            "basic": ["bucket", "bucket_policy", "object"],
        },
        "ec2": {
            "resources": ["instance", "volume", "vpc"],
            "basic": ["instance", "vpc"],
        },
    }
}


def test_normalize_defaults_missing_services_to_basic() -> None:
    result = normalize_provider_service_scope(
        SAMPLE_CATALOG,
        provider="aws",
        services=["s3", "ec2"],
        scope_raw="",
    )
    parsed = json.loads(result)
    assert parsed["s3"]["mode"] == "basic"
    assert parsed["s3"]["resources"] == ["bucket", "bucket_policy", "object"]
    assert parsed["s3"]["additional_resources"] == []
    assert parsed["ec2"]["resources"] == ["instance", "vpc"]


def test_normalize_basic_with_additional_resources() -> None:
    result = normalize_provider_service_scope(
        SAMPLE_CATALOG,
        provider="aws",
        services=["s3"],
        scope_raw={"s3": {"mode": "basic", "additional_resources": ["bucket_acl"]}},
    )
    parsed = json.loads(result)
    assert parsed["s3"]["mode"] == "basic"
    assert parsed["s3"]["additional_resources"] == ["bucket_acl"]
    assert parsed["s3"]["resources"] == ["bucket", "bucket_acl", "bucket_policy", "object"]


def test_normalize_custom_resources() -> None:
    result = normalize_provider_service_scope(
        SAMPLE_CATALOG,
        provider="aws",
        services=["ec2"],
        scope_raw={"ec2": {"mode": "custom", "resources": ["volume", "instance"]}},
    )
    parsed = json.loads(result)
    assert parsed["ec2"]["mode"] == "custom"
    assert parsed["ec2"]["resources"] == ["instance", "volume"]


def test_normalize_rejects_unknown_resource() -> None:
    with pytest.raises(ValueError, match="Invalid resources for aws/s3"):
        normalize_provider_service_scope(
            SAMPLE_CATALOG,
            provider="aws",
            services=["s3"],
            scope_raw={"s3": {"mode": "custom", "resources": ["not_real"]}},
        )


def test_normalize_rejects_invalid_mode() -> None:
    with pytest.raises(ValueError, match="Invalid mode"):
        normalize_provider_service_scope(
            SAMPLE_CATALOG,
            provider="aws",
            services=["s3"],
            scope_raw={"s3": {"mode": "full"}},
        )
