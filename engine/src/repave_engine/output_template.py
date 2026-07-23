from __future__ import annotations

from typing import Any


def format_output_template(template: str, values: dict[str, Any]) -> str:
    format_values = {key: str(value) for key, value in values.items()}
    try:
        return template.format(**format_values)
    except KeyError as exc:
        missing = str(exc).strip("'")
        raise ValueError(
            f"Output template references unknown input placeholder: {missing}"
        ) from exc
