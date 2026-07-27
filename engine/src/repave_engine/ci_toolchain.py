"""Pinned toolchain versions for generated-repo CI (keep aligned with deploy/local/Dockerfile)."""

from __future__ import annotations

TERRAFORM_VERSION = "1.9.8"
TFLINT_VERSION = "0.55.1"
CHECKOV_PIP_SPEC = "checkov>=3.2.0"
PYTHON_VERSION = "3.12"

# GitHub Actions runner images include these; pin when installing in workflow.
HELM_VERSION = "3.14.4"
CONFTEST_VERSION = "0.56.0"
HADOLINT_VERSION = "2.12.0"
GO_VERSION = "1.23"
