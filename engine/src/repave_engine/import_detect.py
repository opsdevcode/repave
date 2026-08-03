"""Guess which golden path an existing repository resembles, from its marker files.

The portal pre-selects the highest scoring candidate so the category and golden path
dropdowns are a confirmation rather than a quiz. Evidence is surfaced verbatim so a wrong
guess is visible and correctable.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from repave_engine.blueprint import Blueprint, artifact_family
from repave_engine.import_rules import matches_glob

_SKIP_DIRS = {".git", ".terraform", "node_modules", "__pycache__", ".venv", ".molecule"}
MAX_SCANNED_FILES = 5000


@dataclass(frozen=True)
class Signal:
    pattern: str
    weight: int = 1
    negative: bool = False


@dataclass(frozen=True)
class BlueprintCandidate:
    blueprint_name: str
    artifact_type: str
    family: str
    confidence: float
    evidence: tuple[str, ...]

    @property
    def percent(self) -> int:
        return round(self.confidence * 100)

    def to_json_dict(self) -> dict[str, object]:
        return {
            "blueprint_name": self.blueprint_name,
            "artifact_type": self.artifact_type,
            "family": self.family,
            "confidence": round(self.confidence, 3),
            "percent": self.percent,
            "evidence": list(self.evidence),
        }


# Patterns are ``**/``-prefixed so a repo that nests its code one level down
# (``terraform/main.tf``, ``roles/foo/tasks/main.yml``) still scores.
_ARTIFACT_SIGNALS: dict[str, tuple[Signal, ...]] = {
    "terraform-module": (
        Signal("**/*.tf", weight=3),
        Signal("**/variables.tf", weight=2),
        Signal("**/outputs.tf", weight=2),
        Signal("**/versions.tf"),
        Signal("**/examples/**"),
        Signal("**/*.tftest.hcl"),
        Signal("**/backend.tf", weight=2, negative=True),
        Signal("**/*.tfbackend", weight=2, negative=True),
    ),
    "terraform-environment-stack": (
        Signal("**/*.tf", weight=2),
        Signal("**/backend.tf", weight=3),
        Signal("**/*.tfbackend", weight=3),
        Signal("**/envs/**", weight=2),
        Signal("**/environments/**", weight=2),
        Signal("**/terraform.tfvars"),
    ),
    "ansible-role": (
        Signal("**/meta/main.yml", weight=3),
        Signal("**/tasks/main.yml", weight=3),
        Signal("**/defaults/main.yml", weight=2),
        Signal("**/handlers/main.yml"),
        Signal("**/molecule/**"),
        Signal("galaxy.yml", weight=3, negative=True),
    ),
    "ansible-collection": (
        Signal("galaxy.yml", weight=4),
        Signal("plugins/**", weight=2),
        Signal("roles/**"),
        Signal("meta/runtime.yml", weight=2),
    ),
    "ansible-playbook-project": (
        Signal("**/ansible.cfg", weight=3),
        Signal("**/playbooks/**", weight=3),
        Signal("**/inventory/**", weight=2),
        Signal("**/requirements.yml"),
        Signal("**/site.yml", weight=2),
        Signal("**/meta/main.yml", weight=2, negative=True),
    ),
    "helm-chart": (
        Signal("**/Chart.yaml", weight=4),
        Signal("**/values.yaml", weight=3),
        Signal("**/templates/**", weight=2),
        Signal("**/.helmignore"),
    ),
    "gitops-deployment": (
        Signal("**/application.y*ml", weight=4),
        Signal("**/kustomization.y*ml", weight=4),
        Signal("**/helmrelease.y*ml", weight=4),
        Signal("**/apps/**", weight=2),
        Signal("**/clusters/**", weight=2),
        Signal("**/Chart.yaml", weight=3, negative=True),
    ),
    "app-service": (
        Signal("**/Dockerfile", weight=3),
        Signal("**/pyproject.toml", weight=2),
        Signal("**/package.json", weight=2),
        Signal("**/go.mod", weight=2),
        Signal("src/**"),
    ),
    "opa-policy": (
        Signal("**/*.rego", weight=4),
        Signal("**/*_test.rego", weight=2),
        Signal("**/policy/**"),
    ),
    "checkov-policy": (
        Signal("**/*.py", weight=2),
        Signal("**/.checkov.yml", weight=3),
        Signal("**/checks/**", weight=3),
        Signal("**/*.rego", weight=3, negative=True),
    ),
    "azure-policy": (
        Signal("**/policy.json", weight=4),
        Signal("**/definitions/**", weight=3),
        Signal("**/azurepolicy*.json", weight=3),
    ),
    "observability": (
        Signal("**/dashboards/**", weight=3),
        Signal("**/monitors/**", weight=3),
        Signal("**/*dashboard*.json", weight=2),
        Signal("**/*monitor*.json", weight=2),
        Signal("**/*.rules.yml", weight=2),
        Signal("**/alerts/**"),
    ),
}

MIN_CONFIDENCE = 0.15


def inventory_relative_paths(repo_dir: Path, *, limit: int = MAX_SCANNED_FILES) -> tuple[str, ...]:
    """List repo-relative POSIX file paths, skipping VCS and vendor directories."""
    paths: list[str] = []
    for path in sorted(repo_dir.rglob("*")):
        if len(paths) >= limit:
            break
        if not path.is_file() or path.is_symlink():
            continue
        try:
            rel = path.relative_to(repo_dir)
        except ValueError:
            continue
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        paths.append(rel.as_posix())
    return tuple(paths)


def _score_artifact_type(
    rel_paths: tuple[str, ...],
    signals: tuple[Signal, ...],
) -> tuple[float, tuple[str, ...]]:
    positives = [signal for signal in signals if not signal.negative]
    total = sum(signal.weight for signal in positives) or 1
    earned = 0
    evidence: list[str] = []

    for signal in signals:
        matched = next((rel for rel in rel_paths if matches_glob(rel, signal.pattern)), None)
        if matched is None:
            continue
        if signal.negative:
            earned -= signal.weight
            continue
        earned += signal.weight
        if matched not in evidence:
            evidence.append(matched)

    confidence = max(0.0, min(1.0, earned / total))
    return confidence, tuple(evidence)


def detect_blueprint_candidates(
    repo_dir: Path,
    blueprints: list[Blueprint],
    *,
    rel_paths: tuple[str, ...] | None = None,
) -> tuple[BlueprintCandidate, ...]:
    """Rank blueprints by how strongly the repo's files match their artifact type."""
    paths = rel_paths if rel_paths is not None else inventory_relative_paths(repo_dir)
    if not paths:
        return ()

    scores: dict[str, tuple[float, tuple[str, ...]]] = {}
    for artifact_type, signals in _ARTIFACT_SIGNALS.items():
        scores[artifact_type] = _score_artifact_type(paths, signals)

    candidates: list[BlueprintCandidate] = []
    for blueprint in blueprints:
        confidence, evidence = scores.get(blueprint.artifact_type, (0.0, ()))
        if confidence < MIN_CONFIDENCE:
            continue
        candidates.append(
            BlueprintCandidate(
                blueprint_name=blueprint.name,
                artifact_type=blueprint.artifact_type,
                family=artifact_family(blueprint.artifact_type),
                confidence=confidence,
                evidence=evidence,
            )
        )

    def rank(candidate: BlueprintCandidate) -> tuple[float, int, str]:
        # Prefer the "-generic" blueprint when several share an artifact type.
        generic_rank = 0 if candidate.blueprint_name.endswith("-generic") else 1
        return (-candidate.confidence, generic_rank, candidate.blueprint_name)

    candidates.sort(key=rank)
    return tuple(candidates)


def best_candidate(candidates: tuple[BlueprintCandidate, ...]) -> BlueprintCandidate | None:
    return candidates[0] if candidates else None
