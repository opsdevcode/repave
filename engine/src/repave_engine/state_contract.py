"""Frozen `/api/state/v1` contract and client skew policy (ADR 004 decision 11).

Pinned `repave-tf` clients live in CI configs across the estate, so this surface is
additive-only within v1: routes and response keys may be added, never removed or
retyped. Breaking changes open `/api/state/v2`.

Skew policy is warn-then-reject. Clients at or above `MIN_SUPPORTED_CLIENT` are served
(with a `Warning` header when behind `CURRENT_CLIENT`); older clients get 426.
Terraform itself never sends the client header, so an absent header is always allowed —
the backend protocol routes must stay usable by a stock `tofu`/`terraform` binary.

This module lives outside `api_state/` on purpose: `repave-cli` imports it, and
`api_state/__init__` pulls in FastAPI. Keep it free of server-only imports.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Final

from repave_engine import __version__

STATE_API_VERSION: Final = "v1"
STATE_API_PREFIX: Final = "/api/state/v1"

#: Client and engine ship lockstep under one semantic-release run (decision 12).
CURRENT_CLIENT: Final = __version__

#: Oldest `repave-tf` this server will serve. Raise only in a major release.
MIN_SUPPORTED_CLIENT: Final = "2.24.0"

CLIENT_HEADER: Final = "X-Repave-Client"
LOCK_ID_PARAM: Final = "ID"

#: Terraform's http backend expects 423 for a held lock; 409 is also accepted.
HTTP_LOCKED: Final = 423
HTTP_CONFLICT: Final = 409
HTTP_UPGRADE_REQUIRED: Final = 426

STATE_API_ENDPOINTS: Final[tuple[str, ...]] = (
    # Terraform http backend protocol (no client header; stock binaries call these).
    "GET /api/state/v1/backend/{tenant}/{state}",
    "POST /api/state/v1/backend/{tenant}/{state}",
    "DELETE /api/state/v1/backend/{tenant}/{state}",
    "LOCK /api/state/v1/backend/{tenant}/{state}",
    "UNLOCK /api/state/v1/backend/{tenant}/{state}",
    # repave-tf client surface.
    "GET /api/state/v1",
    "GET /api/state/v1/states",
    "GET /api/state/v1/states/{tenant}/{state}",
    "GET /api/state/v1/states/{tenant}/{state}/export",
    "POST /api/state/v1/states/{tenant}/{state}/import",
    "GET /api/state/v1/states/{tenant}/{state}/versions",
    "GET /api/state/v1/states/{tenant}/{state}/resources",
    "GET /api/state/v1/states/{tenant}/{state}/graph",
    "GET /api/state/v1/states/{tenant}/{state}/blast-radius",
    "POST /api/state/v1/states/{tenant}/{state}/drift",
    "GET /api/state/v1/states/{tenant}/{state}/inventory",
    "POST /api/state/v1/states/{tenant}/{state}/tx",
    "GET /api/state/v1/tx/{tx_id}",
    "POST /api/state/v1/tx/{tx_id}/preview",
    "POST /api/state/v1/tx/{tx_id}/commit",
    "POST /api/state/v1/tx/{tx_id}/abort",
)

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)")


def parse_version(raw: str) -> tuple[int, int, int] | None:
    """Leading `major.minor.patch` of a version string, or None when unparseable."""
    match = _SEMVER.match(raw.strip())
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


@dataclass(frozen=True)
class ClientCompatibility:
    """Outcome of checking a client version against the skew policy."""

    supported: bool
    warning: str = ""

    @property
    def rejected(self) -> bool:
        return not self.supported


def evaluate_client_version(raw: str | None) -> ClientCompatibility:
    """Apply the warn-then-reject policy to a client version header.

    An absent or unparseable version is allowed: stock Terraform sends no header, and
    refusing to serve state over a header we invented would be a self-inflicted outage.
    """
    if raw is None or not raw.strip():
        return ClientCompatibility(supported=True)

    client = parse_version(raw)
    if client is None:
        return ClientCompatibility(
            supported=True,
            warning=f'299 - "unrecognized {CLIENT_HEADER} {raw!r}; assuming current"',
        )

    floor = parse_version(MIN_SUPPORTED_CLIENT)
    current = parse_version(CURRENT_CLIENT)
    if floor is not None and client < floor:
        return ClientCompatibility(supported=False)
    if current is not None and client < current:
        return ClientCompatibility(
            supported=True,
            warning=(
                f'299 - "repave-tf {raw.strip()} is behind server {CURRENT_CLIENT}; '
                f'upgrade before {MIN_SUPPORTED_CLIENT} support is dropped"'
            ),
        )
    return ClientCompatibility(supported=True)


def upgrade_required_detail(raw: str) -> str:
    return (
        f"repave-tf {raw.strip()} is older than the minimum supported client "
        f"{MIN_SUPPORTED_CLIENT}; upgrade to {CURRENT_CLIENT}"
    )


def contract_payload() -> dict[str, object]:
    """Discovery document served at `GET /api/state/v1`."""
    return {
        "api_version": STATE_API_VERSION,
        "server_version": __version__,
        "current_client": CURRENT_CLIENT,
        "min_supported_client": MIN_SUPPORTED_CLIENT,
        "client_header": CLIENT_HEADER,
        "endpoints": list(STATE_API_ENDPOINTS),
    }
