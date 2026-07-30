from __future__ import annotations

import pytest

from repave_engine.worker_mode import WorkerMode, parse_worker_mode


def test_parse_worker_mode_inline() -> None:
    assert parse_worker_mode("inline") == WorkerMode.INLINE
    assert parse_worker_mode("inprocess") == WorkerMode.INLINE


def test_parse_worker_mode_external_aliases() -> None:
    assert parse_worker_mode("external") == WorkerMode.EXTERNAL
    assert parse_worker_mode("kubernetes") == WorkerMode.EXTERNAL


def test_parse_worker_mode_job() -> None:
    assert parse_worker_mode("job") == WorkerMode.JOB


def test_parse_worker_mode_invalid() -> None:
    with pytest.raises(ValueError, match="worker_mode"):
        parse_worker_mode("redis")
