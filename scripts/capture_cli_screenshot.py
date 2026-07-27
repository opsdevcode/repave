#!/usr/bin/env python3
"""Capture CLI dry-run PNG for docs/images/cli/."""
from __future__ import annotations

import html
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/images/cli/generate-dry-run.png"

ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


def _run_cli() -> str:
    env = os.environ.copy()
    env.setdefault("REPAVE_GITHUB_ORG", "opsdevcode")
    env.setdefault("REPAVE_MODULES_ROOT", str(Path.home() / "repave-modules"))
    cmd = [
        "uv",
        "run",
        "repave",
        "generate",
        "--repo-root",
        str(ROOT),
        "--blueprint",
        "blueprints/terraform-module-generic",
        "--dry-run",
        "--input",
        "module_name=readme-demo",
        "--input",
        'description=README screenshot module',
        "--input",
        "cloud_provider=aws",
        "--input",
        "provider_services=ec2,s3",
    ]
    completed = subprocess.run(
        cmd,
        cwd=ROOT / "engine",
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    combined = (completed.stdout or "") + (completed.stderr or "")
    text = _strip_ansi(combined)
    if "Blueprint:" not in text:
        print(text[:4000], file=sys.stderr)
        raise RuntimeError(f"repave generate failed (exit {completed.returncode})")
    start = text.find("Blueprint:")
    body = text[start:].strip()
    lines = body.splitlines()
    max_lines = 28
    if len(lines) > max_lines:
        lines = lines[: max_lines - 1] + ["  …"]
    return "\n".join(lines)


def _terminal_html(command: str, output: str) -> str:
    safe_cmd = html.escape(f"$ {command}")
    safe_out = html.escape(output)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <style>
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      padding: 24px;
      background: #0d1117;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }}
    .window {{
      max-width: 920px;
      margin: 0 auto;
      border-radius: 10px;
      overflow: hidden;
      border: 1px solid #30363d;
      box-shadow: 0 12px 40px rgba(0,0,0,0.45);
    }}
    .titlebar {{
      background: #161b22;
      padding: 10px 14px;
      display: flex;
      align-items: center;
      gap: 8px;
      border-bottom: 1px solid #30363d;
    }}
    .dot {{ width: 12px; height: 12px; border-radius: 50%; }}
    .dot--r {{ background: #ff5f57; }}
    .dot--y {{ background: #febc2e; }}
    .dot--g {{ background: #28c840; }}
    .title {{
      flex: 1;
      text-align: center;
      font-size: 12px;
      color: #8b949e;
      margin-right: 52px;
    }}
    pre {{
      margin: 0;
      padding: 18px 20px 22px;
      font-size: 13px;
      line-height: 1.45;
      color: #e6edf3;
      white-space: pre-wrap;
      word-break: break-word;
      background: #0d1117;
    }}
    .prompt {{ color: #7ee787; }}
    .muted {{ color: #8b949e; }}
  </style>
</head>
<body>
  <div class="window">
    <div class="titlebar">
      <span class="dot dot--r"></span>
      <span class="dot dot--y"></span>
      <span class="dot dot--g"></span>
      <span class="title">repave — generate (dry-run)</span>
    </div>
    <pre><span class="prompt">{safe_cmd}</span>
<span class="muted"># same gates and layout as the portal plan flow</span>

{safe_out}</pre>
  </div>
</body>
</html>"""


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        print("Install playwright: cd engine && uv run --with playwright python …", file=sys.stderr)
        raise SystemExit(1) from exc

    output = _run_cli()
    command = (
        "repave generate --blueprint blueprints/terraform-module-generic --dry-run "
        "--input module_name=readme-demo …"
    )
    page_html = _terminal_html(command, output)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 980, "height": 720})
        page.set_content(page_html, wait_until="networkidle")
        page.screenshot(path=str(OUT), full_page=True)
        browser.close()
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
