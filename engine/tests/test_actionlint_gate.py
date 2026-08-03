from __future__ import annotations

from pathlib import Path

from repave_engine.gates import run_gates


def test_actionlint_skips_when_tool_missing(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        "name: ci\non: push\njobs: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name != "actionlint",
    )
    results = run_gates(tmp_path, ("actionlint",))
    actionlint = next(result for result in results if result.name == "actionlint")
    assert actionlint.skipped
    assert "not installed" in actionlint.message


def test_actionlint_passes_on_valid_workflow(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".github" / "workflows").mkdir(parents=True)
    (tmp_path / ".github" / "workflows" / "ci.yml").write_text(
        "\n".join(
            [
                "name: ci",
                "on:",
                "  push:",
                "    branches: [main]",
                "permissions:",
                "  contents: read",
                "jobs:",
                "  lint:",
                "    runs-on: ubuntu-latest",
                "    steps:",
                "      - uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
            ]
        ),
        encoding="utf-8",
    )

    def fake_run(cmd: list[str], cwd: Path, **kwargs):
        from subprocess import CompletedProcess

        assert cmd[0] == "actionlint"
        assert ".github/workflows/ci.yml" in cmd
        return CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda name: name == "actionlint",
    )
    monkeypatch.setattr("repave_engine.gate_runners.run_command", fake_run)

    results = run_gates(tmp_path, ("actionlint",))
    actionlint = next(result for result in results if result.name == "actionlint")
    assert actionlint.passed
    assert not actionlint.skipped


def test_actionlint_skips_when_no_workflows(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "repave_engine.gate_runners.tool_available",
        lambda _name: True,
    )
    results = run_gates(tmp_path, ("actionlint",))
    actionlint = next(result for result in results if result.name == "actionlint")
    assert actionlint.skipped
    assert "no workflow files" in actionlint.message
