#!/usr/bin/env python3
"""Write a repave control-plane license JSON for a paying customer."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

PRODUCT_ID = "repave-control-plane"
ALLOWED_SKUS = frozenset({"pilot", "annual"})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--organization",
        required=True,
        help="Customer GitHub org or legal name (stored in the file)",
    )
    parser.add_argument("--sku", required=True, choices=sorted(ALLOWED_SKUS))
    parser.add_argument("--expires", required=True, help="YYYY-MM-DD (UTC date)")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    date.fromisoformat(args.expires)
    payload = {
        "product": PRODUCT_ID,
        "organization": args.organization.strip(),
        "sku": args.sku,
        "expires": args.expires,
    }
    if not payload["organization"]:
        raise SystemExit("organization is empty")
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
