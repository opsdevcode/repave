"""Gated assistant artifact drafts — candidate files, never publish."""

from __future__ import annotations

import json
import logging
import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from repave_engine.assistant import AssistantResolution
from repave_engine.assistant_draft import AssistantDraftModel, prompt_hash
from repave_engine.blueprint import Blueprint
from repave_engine.gates import all_gates_passed, run_gates
from repave_engine.infracost_policy import effective_gate_names
from repave_engine.safe_paths import confined_join
from repave_engine.settings import load_gate_overrides

logger = logging.getLogger(__name__)

_MAX_FILES = 12
_MAX_FILE_CHARS = 32_000
_JSON_FENCE = re.compile(r"```(?:json)?\s*(\{.*\})\s*```", re.DOTALL)
ARTIFACT_SYSTEM = (
    'Reply with JSON only: {"files":{"relative/path":"contents"}}. '
    "Use relative paths only. Empty files object if the catalog form is enough. "
    "Never include generate, dry_run, secrets, or gate results."
)


@dataclass(frozen=True)
class ArtifactFile:
    path: str
    content: str

    def to_public_dict(self) -> dict[str, str]:
        return {"path": self.path, "content": self.content}


def parse_artifact_files(raw: str) -> tuple[ArtifactFile, ...]:
    """Parse a files mapping. Rejects traversal and blocked keys before any write."""
    text = raw.strip()
    fenced = _JSON_FENCE.search(text)
    if fenced:
        text = fenced.group(1)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError("assistant artifacts must be a JSON object") from exc
    if not isinstance(payload, dict):
        raise ValueError("assistant artifacts must be a JSON object")
    for blocked in ("generate", "dry_run", "content"):
        if blocked in payload:
            raise ValueError(f"assistant artifacts must not include {blocked}")
    files_raw = payload.get("files", {})
    if files_raw is None:
        return ()
    if not isinstance(files_raw, dict):
        raise ValueError("assistant artifacts files must be an object")
    if len(files_raw) > _MAX_FILES:
        raise ValueError(f"assistant artifacts exceed {_MAX_FILES} files; remove extras")
    parsed: list[ArtifactFile] = []
    for key, value in files_raw.items():
        relative = str(key).strip().replace("\\", "/")
        _reject_unsafe_path(relative)
        if not isinstance(value, str):
            raise ValueError(f"assistant artifact {relative!r} content must be a string")
        if len(value) > _MAX_FILE_CHARS:
            raise ValueError(
                f"assistant artifact {relative!r} exceeds {_MAX_FILE_CHARS} characters"
            )
        parsed.append(ArtifactFile(path=relative, content=value))
    return tuple(parsed)


def apply_artifact_draft(
    resolution: AssistantResolution,
    *,
    blueprints: Sequence[Blueprint],
    model: AssistantDraftModel,
    model_id: str,
    repo_root: Path,
) -> AssistantResolution:
    """Materialize candidate files and run the matched blueprint gates. Never publishes."""
    chosen = _chosen_blueprint(resolution, blueprints)
    if chosen is None:
        return replace(resolution, artifact_status="skipped-no-blueprint")
    prompt = _build_artifact_prompt(intent=resolution.intent, blueprint=chosen)
    digest = prompt_hash(prompt)
    try:
        raw = model.complete(prompt, system=ARTIFACT_SYSTEM)
        files = parse_artifact_files(raw)
    except ValueError as exc:
        logger.warning("assistant artifacts rejected: %s", exc)
        return replace(
            resolution,
            prompt_hash=resolution.prompt_hash or digest,
            artifact_status="rejected",
            draft_model=resolution.draft_model or model_id,
        )
    if not files:
        return replace(
            resolution,
            prompt_hash=resolution.prompt_hash or digest,
            artifact_status="skipped-empty",
            draft_model=resolution.draft_model or model_id,
        )
    gates, passed = _gate_candidate_files(files, blueprint=chosen, repo_root=repo_root)
    tools = tuple(dict.fromkeys((*resolution.tools, "catalog.artifacts")))
    public_files = files if passed else ()
    status = "gated" if passed else "blocked"
    return replace(
        resolution,
        prompt_hash=resolution.prompt_hash or digest,
        draft_model=resolution.draft_model or model_id,
        artifact_status=status,
        artifact_gates=gates,
        artifact_files=public_files,
        tools=tools,
    )


def _reject_unsafe_path(relative: str) -> None:
    if not relative or relative.endswith("/"):
        raise ValueError("assistant artifact paths must be relative files")
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"assistant artifact path {relative!r} must stay relative without '..'")
    staging = Path("/assistant-artifact-root")
    confined_join(staging, *candidate.parts)


def _chosen_blueprint(
    resolution: AssistantResolution,
    blueprints: Sequence[Blueprint],
) -> Blueprint | None:
    by_name = {item.name: item for item in blueprints}
    if resolution.matches:
        return by_name.get(resolution.matches[0].blueprint)
    return None


def _build_artifact_prompt(*, intent: str, blueprint: Blueprint) -> str:
    return "\n".join(
        (
            "If the catalog form cannot express the intent, propose candidate files "
            f"for golden path {blueprint.name}.",
            'Otherwise return {"files":{}}.',
            f"Intent: {intent.strip()}",
            "Do not publish or score gates.",
        )
    )


def _gate_candidate_files(
    files: Sequence[ArtifactFile],
    *,
    blueprint: Blueprint,
    repo_root: Path,
) -> tuple[tuple[dict[str, object], ...], bool]:
    overrides = load_gate_overrides(repo_root)
    names = effective_gate_names(blueprint, overrides)
    with tempfile.TemporaryDirectory(prefix="repave-assistant-artifacts-") as tmp:
        staging = Path(tmp)
        for item in files:
            dest = confined_join(staging, *Path(item.path).parts)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(item.content, encoding="utf-8")
        results = run_gates(
            staging,
            names,
            blueprint=blueprint,
            gate_overrides=overrides,
            require_run=True,
            repo_root=repo_root,
        )
    gates = tuple(
        {
            "name": item.name,
            "passed": item.passed,
            "skipped": item.skipped,
            "message": item.message,
        }
        for item in results
    )
    return gates, all_gates_passed(results) and bool(results)
