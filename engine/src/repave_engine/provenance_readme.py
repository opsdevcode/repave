"""README provenance section sync (v1.23 generation visibility)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from repave_engine.blueprint import Blueprint
from repave_engine.provenance import build_provenance_document
from repave_engine.safe_paths import confined_join, trusted_path


def _line_items(blueprint: Blueprint, document: dict[str, Any]) -> list[str]:
    spec = document.get("spec", {})
    if not isinstance(spec, dict):
        return []
    lines = [
        f"- **Blueprint:** `{spec.get('blueprint', {}).get('name', blueprint.name)}` "
        f"@ `{spec.get('blueprint', {}).get('version', blueprint.version)}`",
        f"- **Standard:** `{spec.get('standard', {}).get('source', blueprint.standard_source)}` "
        f"@ `{spec.get('standard', {}).get('version', blueprint.standard_version)}`",
        f"- **Engine:** `{spec.get('generation', {}).get('engine_version', '')}` "
        f"(generated `{spec.get('generation', {}).get('generated_at', '')}`)",
    ]
    checkov = spec.get("checkov")
    if isinstance(checkov, dict):
        lines.append(
            f"- **Checkov pack:** `{checkov.get('policies_source', '')}` "
            f"@ `{checkov.get('policy_version', '')}`"
        )
    opa = spec.get("opa")
    if isinstance(opa, dict):
        lines.append(
            f"- **OPA policies:** `{opa.get('policies_source', '')}` "
            f"@ `{opa.get('policy_version', '')}`"
        )
    policy = spec.get("policy")
    if isinstance(policy, dict):
        profile = policy.get("profile", "")
        pack = policy.get("pack_source", "")
        if profile or pack:
            lines.append(f"- **Policy profile:** `{profile}` (pack `{pack}`)")
    lines.append(
        "- **Canonical record:** `repave.yaml` (`provenance-drift` gate validates this file)"
    )
    return lines


def provenance_section_markdown(blueprint: Blueprint, values: dict[str, Any]) -> str:
    document = build_provenance_document(blueprint, values)
    body = "\n".join(_line_items(blueprint, document))
    return f"## Provenance\n\n{body}\n"


def sync_readme_provenance_section(
    output_dir: Path,
    blueprint: Blueprint,
    values: dict[str, Any],
) -> None:
    readme = confined_join(trusted_path(output_dir), "README.md")
    if not readme.is_file():
        return

    section = provenance_section_markdown(blueprint, values)
    content = readme.read_text(encoding="utf-8")
    pattern = re.compile(r"^## Provenance\b[\s\S]*?(?=^## |\Z)", re.MULTILINE)

    if pattern.search(content):
        updated = pattern.sub(section + "\n", content, count=1)
    else:
        updated = content.rstrip() + "\n\n" + section

    readme.write_text(updated, encoding="utf-8")
