"""Scan a GitHub organization and classify repositories for batch import."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from repave_engine.blueprint import _ARTIFACT_FAMILY_ORDER, blueprints_dir, list_blueprints
from repave_engine.fleet import normalize_repo_url
from repave_engine.github_inventory import (
    GitHubInventoryError,
    inventory_github_paths,
    list_org_repositories,
    remote_has_provenance,
)
from repave_engine.import_detect import (
    BlueprintCandidate,
    best_candidate,
    detect_blueprint_candidates,
)

DEFAULT_SCAN_LIMIT = 100
DEFAULT_MIN_CONFIDENCE = 0.0
SCAN_ARTIFACT_FAMILIES: frozenset[str] = frozenset(_ARTIFACT_FAMILY_ORDER)


@dataclass(frozen=True)
class ScannedRepository:
    url: str
    owner: str
    name: str
    governed: bool
    classification_error: str | None
    top_candidate: BlueprintCandidate | None

    def to_json_dict(self) -> dict[str, object]:
        return {
            "url": self.url,
            "owner": self.owner,
            "name": self.name,
            "governed": self.governed,
            "classification_error": self.classification_error,
            "top_candidate": (
                self.top_candidate.to_json_dict() if self.top_candidate is not None else None
            ),
        }


@dataclass(frozen=True)
class OrgScanResult:
    org: str
    listed: int
    limit: int
    truncated: bool
    repos: tuple[ScannedRepository, ...]

    def to_json_dict(self) -> dict[str, object]:
        return {
            "org": self.org,
            "listed": self.listed,
            "limit": self.limit,
            "truncated": self.truncated,
            "repos": [repo.to_json_dict() for repo in self.repos],
        }


def classify_remote_repository(
    owner: str,
    repo: str,
    token: str,
    repo_root: Path,
    *,
    ref: str | None = None,
) -> ScannedRepository:
    """Classify a remote repository via the trees API and marker-file detection."""
    url = normalize_repo_url(f"https://github.com/{owner}/{repo}")
    governed = remote_has_provenance(owner, repo, token, ref=ref)
    if governed:
        return ScannedRepository(
            url=url,
            owner=owner,
            name=repo,
            governed=True,
            classification_error=None,
            top_candidate=None,
        )
    try:
        rel_paths = inventory_github_paths(owner, repo, token, ref=ref)
    except GitHubInventoryError as exc:
        return ScannedRepository(
            url=url,
            owner=owner,
            name=repo,
            governed=False,
            classification_error=str(exc),
            top_candidate=None,
        )
    if not rel_paths:
        return ScannedRepository(
            url=url,
            owner=owner,
            name=repo,
            governed=False,
            classification_error="repository has no scannable files",
            top_candidate=None,
        )
    catalog = list_blueprints(blueprints_dir(repo_root))
    candidates = detect_blueprint_candidates(Path("."), catalog, rel_paths=rel_paths)
    top = best_candidate(candidates)
    return ScannedRepository(
        url=url,
        owner=owner,
        name=repo,
        governed=False,
        classification_error=None,
        top_candidate=top,
    )


def _matches_scan_filters(
    scanned: ScannedRepository,
    *,
    families: frozenset[str],
    skip_governed: bool,
    min_confidence: float,
) -> bool:
    if skip_governed and scanned.governed:
        return False
    if scanned.classification_error:
        return not families
    candidate = scanned.top_candidate
    if candidate is None:
        return not families
    if candidate.confidence < min_confidence:
        return False
    return not families or candidate.family in families


def scan_github_org(
    org: str,
    repo_root: Path,
    token: str,
    *,
    families: frozenset[str] | None = None,
    skip_governed: bool = True,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    limit: int = DEFAULT_SCAN_LIMIT,
) -> OrgScanResult:
    """List org repositories, classify each, and return rows matching scan filters."""
    org_name = org.strip()
    if not org_name:
        raise ValueError("org is required to scan GitHub repositories")
    if limit <= 0:
        raise ValueError("limit must be positive")
    family_filter = frozenset(families or ())
    if family_filter:
        unknown = family_filter - SCAN_ARTIFACT_FAMILIES
        if unknown:
            raise ValueError(
                f"unknown artifact families: {', '.join(sorted(unknown))}; "
                f"expected one of {', '.join(sorted(SCAN_ARTIFACT_FAMILIES))}"
            )
    listed_repos = list_org_repositories(org_name, token, limit=limit)
    truncated = len(listed_repos) >= limit
    scanned_rows: list[ScannedRepository] = []
    for entry in listed_repos:
        row = classify_remote_repository(entry.owner, entry.name, token, repo_root)
        if _matches_scan_filters(
            row,
            families=family_filter,
            skip_governed=skip_governed,
            min_confidence=min_confidence,
        ):
            scanned_rows.append(row)
    return OrgScanResult(
        org=org_name,
        listed=len(listed_repos),
        limit=limit,
        truncated=truncated,
        repos=tuple(scanned_rows),
    )
