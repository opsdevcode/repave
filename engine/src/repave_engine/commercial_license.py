"""Paid grant for hosted (service-mode) repave. Local Compose stays unlimited."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

PRODUCT_ID = "repave-control-plane"
ALLOWED_SKUS = frozenset({"pilot", "annual"})


@dataclass(frozen=True)
class CommercialLicense:
    product: str
    organization: str
    sku: str
    expires: date
    path: Path


def _parse_expires(raw: object) -> date:
    text = str(raw).strip()
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise ValueError(
            f"license expires must be YYYY-MM-DD (got {text!r}); re-issue the file"
        ) from exc


def load_commercial_license(*, service_enabled: bool) -> CommercialLicense | None:
    """Require REPAVE_LICENSE_FILE when service mode is on. Local mode skips."""
    if not service_enabled:
        return None
    raw_path = os.environ.get("REPAVE_LICENSE_FILE", "").strip()
    if not raw_path:
        raise ValueError(
            "auth.service_mode requires a paid license file: set REPAVE_LICENSE_FILE "
            "to the JSON path (see docs/customers/install.md)"
        )
    path = Path(raw_path).expanduser()
    if not path.is_file():
        raise ValueError(
            f"license file not found: {path} (set REPAVE_LICENSE_FILE to an existing file)"
        )
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"license file is not valid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"license file must be a JSON object: {path}")
    product = str(payload.get("product", "")).strip()
    organization = str(payload.get("organization", "")).strip()
    sku = str(payload.get("sku", "")).strip().lower()
    if product != PRODUCT_ID:
        raise ValueError(
            f"license product must be {PRODUCT_ID!r} (got {product!r}); re-issue the file"
        )
    if not organization:
        raise ValueError("license organization is empty; re-issue with the customer GitHub org")
    if sku not in ALLOWED_SKUS:
        allowed = ", ".join(sorted(ALLOWED_SKUS))
        raise ValueError(f"license sku must be one of {allowed} (got {sku!r})")
    expires = _parse_expires(payload.get("expires"))
    today = datetime.now(UTC).date()
    if expires < today:
        raise ValueError(
            f"license for {organization} expired on {expires.isoformat()}; "
            "set REPAVE_LICENSE_FILE to a renewed file"
        )
    return CommercialLicense(
        product=product,
        organization=organization,
        sku=sku,
        expires=expires,
        path=path,
    )
