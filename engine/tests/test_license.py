from __future__ import annotations

from repave_engine.pipeline import generate_from_blueprint


def test_render_none_license_omits_license_file(
    terraform_blueprint,
    output_config,
    staging_root,
) -> None:
    inputs = {
        "module_name": "example",
        "description": "Example module generated in tests",
        "cloud_provider": "aws",
        "provider_services": "s3,vpc",
        "license": "none",
    }
    result = generate_from_blueprint(
        terraform_blueprint,
        inputs,
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
    )

    paths = {item.path for item in result.rendered_files}
    assert "LICENSE" not in paths
    readme = next(item for item in result.rendered_files if item.path == "README.md")
    assert "No license is provided" in readme.content


def test_render_proprietary_license_includes_license_file(
    terraform_blueprint,
    output_config,
    staging_root,
) -> None:
    inputs = {
        "module_name": "example",
        "description": "Example module generated in tests",
        "cloud_provider": "aws",
        "provider_services": "s3,vpc",
        "license": "proprietary",
    }
    result = generate_from_blueprint(
        terraform_blueprint,
        inputs,
        output_config=output_config,
        dry_run=True,
        staging_root=staging_root,
    )

    license_file = next(item for item in result.rendered_files if item.path == "LICENSE")
    assert "All rights reserved" in license_file.content
    readme = next(item for item in result.rendered_files if item.path == "README.md")
    assert "Proprietary software license" in readme.content
