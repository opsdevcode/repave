"""Parse and validate Terraform/OpenTofu state documents (state format version 4).

Unknown formats are rejected rather than guessed at (ADR 004 decision 10). Guessing
at a format we do not understand risks writing back a document that silently drops
resources, which is worse than refusing the write.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Final

SUPPORTED_STATE_VERSIONS: Final[frozenset[int]] = frozenset({4})


class StateDocumentError(ValueError):
    """A payload is not a state document this store can accept."""


@dataclass(frozen=True)
class StateDocument:
    """A parsed state document plus the exact bytes it came from.

    `raw` is retained so the store can persist byte-for-byte what the client sent;
    re-serializing parsed JSON would reorder keys and break byte-exact export.
    """

    raw: bytes
    payload: dict[str, Any]

    @property
    def version(self) -> int:
        return int(self.payload["version"])

    @property
    def serial(self) -> int:
        return int(self.payload.get("serial", 0))

    @property
    def lineage(self) -> str:
        return str(self.payload.get("lineage", ""))

    @property
    def terraform_version(self) -> str:
        return str(self.payload.get("terraform_version", ""))

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.raw).hexdigest()

    @property
    def size(self) -> int:
        return len(self.raw)

    def resources(self) -> list[dict[str, Any]]:
        items = self.payload.get("resources")
        if not isinstance(items, list):
            return []
        return [item for item in items if isinstance(item, dict)]

    def outputs(self) -> dict[str, Any]:
        block = self.payload.get("outputs")
        return block if isinstance(block, dict) else {}


def parse_state_document(raw: bytes) -> StateDocument:
    """Parse state bytes, raising `StateDocumentError` for anything unusable."""
    if not raw.strip():
        raise StateDocumentError("state document is empty")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise StateDocumentError("state document is not valid UTF-8") from exc
    except json.JSONDecodeError as exc:
        raise StateDocumentError(f"state document is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise StateDocumentError("state document must be a JSON object")

    raw_version = payload.get("version")
    if not isinstance(raw_version, int) or isinstance(raw_version, bool):
        raise StateDocumentError("state document is missing an integer `version` field")
    if raw_version not in SUPPORTED_STATE_VERSIONS:
        supported = ", ".join(str(item) for item in sorted(SUPPORTED_STATE_VERSIONS))
        raise StateDocumentError(
            f"unsupported state format version {raw_version}; this store supports {supported}. "
            "Upgrade repave or downgrade the IaC binary that produced it"
        )

    serial = payload.get("serial", 0)
    if not isinstance(serial, int) or isinstance(serial, bool) or serial < 0:
        raise StateDocumentError("state document `serial` must be a non-negative integer")

    lineage = payload.get("lineage")
    if not isinstance(lineage, str) or not lineage.strip():
        raise StateDocumentError("state document is missing a non-empty `lineage`")

    return StateDocument(raw=raw, payload=payload)
