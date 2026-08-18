from __future__ import annotations

import importlib.util
from pathlib import Path

_FILTER = Path(__file__).resolve().parents[2] / ".github" / "codeql" / "filter_sarif.py"


def _mod():
    spec = importlib.util.spec_from_file_location("filter_sarif", _FILTER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _result(uri: str, rule: str) -> dict:
    return {
        "ruleId": rule,
        "locations": [{"physicalLocation": {"artifactLocation": {"uri": uri}}}],
    }


def test_filter_drops_path_injection_on_safe_paths_helper() -> None:
    mod = _mod()
    payload = {
        "runs": [
            {
                "results": [
                    _result("engine/src/repave_engine/safe_paths.py", "py/path-injection"),
                    _result("engine/src/repave_engine/render.py", "py/path-injection"),
                ]
            }
        ]
    }
    assert mod.filter_sarif(payload) == 1
    kept = payload["runs"][0]["results"]
    assert len(kept) == 1
    assert kept[0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"].endswith(
        "render.py"
    )


def test_filter_drops_command_injection_on_subprocess_helper() -> None:
    mod = _mod()
    assert mod.should_drop(
        _result("engine/src/repave_engine/subprocess_run.py", "py/command-line-injection")
    )
    assert not mod.should_drop(
        _result("engine/src/repave_engine/gate_runners.py", "py/command-line-injection")
    )


def test_filter_drops_dom_xss_on_portal_bundle() -> None:
    mod = _mod()
    assert mod.should_drop(
        _result("engine/src/repave_engine/static/repave.js", "js/xss-through-dom")
    )
    assert not mod.should_drop(_result("backstage/packages/app/src/App.tsx", "js/xss-through-dom"))
