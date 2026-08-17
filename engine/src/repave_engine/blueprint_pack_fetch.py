"""Materialize git- or OCI-backed blueprint packs into a local cache."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from repave_engine.git_clone import CloneError, resolve_git_token, shallow_clone
from repave_engine.oci_pull import OciPullError, is_oci_pack_url, pull_oci_artifact
from repave_engine.settings import (
    BlueprintPackConfig,
    BlueprintPackSource,
    load_blueprint_pack_config,
)

logger = logging.getLogger(__name__)


def pack_cache_name(source: BlueprintPackSource) -> str:
    """Stable cache folder: dest when set, else a short hash of url + ref."""
    if source.dest:
        return source.dest
    digest = hashlib.sha256(f"{source.url}\0{source.ref}".encode()).hexdigest()
    return digest[:16]


def catalog_root_for_source(source: BlueprintPackSource, cache_dir: Path) -> Path:
    """Return the catalog directory inside the clone (clone root or subdir)."""
    clone_dir = (cache_dir / pack_cache_name(source)).resolve()
    if source.subdir in (".", ""):
        return clone_dir
    catalog = (clone_dir / source.subdir).resolve()
    try:
        catalog.relative_to(clone_dir)
    except ValueError as exc:
        raise ValueError(
            f"blueprint_packs.sources[].subdir {source.subdir!r} escapes the clone directory"
        ) from exc
    return catalog


def _clone_dir_ready(clone_dir: Path) -> bool:
    return clone_dir.is_dir() and any(clone_dir.iterdir())


def _ensure_clone(source: BlueprintPackSource, clone_dir: Path) -> bool:
    if _clone_dir_ready(clone_dir):
        return True
    token = source.token or resolve_git_token()
    try:
        if is_oci_pack_url(source.url):
            pull_oci_artifact(source.url, clone_dir, ref=source.ref, token=token)
        else:
            shallow_clone(source.url, clone_dir, token=token, ref=source.ref)
    except (CloneError, OciPullError) as exc:
        action = "pull" if is_oci_pack_url(source.url) else "clone"
        logger.warning(
            "blueprint pack %s skipped for %s ref %s: %s "
            "(delete %s to retry after fixing auth or the URL)",
            action,
            source.url,
            source.ref,
            exc,
            clone_dir,
        )
        return False
    return clone_dir.is_dir()


def materialize_blueprint_pack_roots(
    repo_root: Path,
    *,
    config: BlueprintPackConfig | None = None,
) -> tuple[Path, ...]:
    """Clone or pull missing packs; return catalog roots in config order.

    Existing cache directories are reused (no fetch). Delete a cache folder to
    refresh. Clone/pull failures log a warning and skip that pack.
    """
    cfg = config if config is not None else load_blueprint_pack_config(repo_root)
    if cfg is None or not cfg.sources:
        return ()

    roots: list[Path] = []
    seen: set[Path] = set()
    for source in cfg.sources:
        clone_dir = (cfg.cache_dir / pack_cache_name(source)).resolve()
        catalog = catalog_root_for_source(source, cfg.cache_dir)
        if not _ensure_clone(source, clone_dir):
            continue
        if not catalog.is_dir():
            logger.warning(
                "blueprint pack %s ref %s: catalog root %s is missing; "
                "check blueprint_packs.sources[].subdir",
                source.url,
                source.ref,
                catalog,
            )
            continue
        if catalog in seen:
            continue
        seen.add(catalog)
        roots.append(catalog)
    return tuple(roots)
