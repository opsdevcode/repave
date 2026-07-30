from __future__ import annotations

import argparse
from pathlib import Path

from repave_engine.doctor import (
    doctor_exit_code,
    format_doctor_report,
    load_blueprint_tools,
    run_doctor,
)


def cmd_doctor(args: argparse.Namespace) -> int:
    root = Path(args.repo_root).resolve()
    tools = None
    blueprint = (getattr(args, "blueprint", None) or "").strip()
    if blueprint:
        blueprint_path = Path(blueprint)
        if not blueprint_path.is_absolute():
            blueprint_path = (root / blueprint_path).resolve()
        tools = load_blueprint_tools(blueprint_path, repo_root=root)
    results = run_doctor(tools=tools, all_pins=bool(getattr(args, "all_pins", False)))
    print(format_doctor_report(results))
    return doctor_exit_code(results, strict=bool(args.strict))
