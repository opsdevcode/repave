from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

from repave_engine.cli._common import _load_output_config_from_args


def cmd_run_worker(args: argparse.Namespace) -> int:
    from repave_engine.run_queue import RunQueueConfig, build_run_queue
    from repave_engine.run_store import RunStatus
    from repave_engine.settings import load_durability_config

    repo_root = Path(args.repo_root).resolve()
    durability = load_durability_config(repo_root)
    if durability is None:
        raise SystemExit(
            "durability.async_generation must be enabled (or REPAVE_ASYNC_GENERATION=1)"
        )

    output_config = _load_output_config_from_args(args)
    queue = build_run_queue(
        repo_root,
        output_config,
        RunQueueConfig(
            max_concurrent_runs=durability.max_concurrent_runs,
            queue_max_depth=durability.queue_max_depth,
            db_path=durability.runs_db,
            external_workers=True,
            max_attempts=durability.max_run_attempts,
            stale_run_seconds=durability.run_stale_seconds,
            retry_base_seconds=durability.run_retry_base_seconds,
        ),
    )
    try:
        if args.run_id:
            record = queue.get(args.run_id)
            if record is None:
                raise SystemExit(f"unknown run_id: {args.run_id}")
            if record.status == RunStatus.QUEUED:
                queue._store.update_status(args.run_id, RunStatus.RUNNING)
            queue.process_run(args.run_id, record.acting_user)
            return 0
        while True:
            if queue.claim_and_process():
                if args.once:
                    return 0
                continue
            if args.once:
                return 0
            time.sleep(args.poll_interval)
    finally:
        queue.close(wait=True)


SERVER_EXTRA_HINT = (
    "repave serve requires the server extra: install repave-engine[server] "
    "(or run `uv sync --extra server` from engine/)"
)


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn

        from repave_engine.api import create_app
    except ImportError as exc:
        raise SystemExit(f"{SERVER_EXTRA_HINT}\nmissing dependency: {exc.name}") from exc

    repo_root = Path(args.repo_root).resolve()
    if args.reload:
        os.environ["REPAVE_SERVE_REPO_ROOT"] = str(repo_root)
        reload_dir = repo_root / "engine" / "src"
        uvicorn.run(
            "repave_engine.api:create_app_for_serve",
            factory=True,
            host=args.host,
            port=args.port,
            reload=True,
            reload_dirs=[str(reload_dir)] if reload_dir.is_dir() else None,
        )
    else:
        output_config = _load_output_config_from_args(args)
        app = create_app(repo_root=repo_root, output_config=output_config)
        uvicorn.run(app, host=args.host, port=args.port)
    return 0
