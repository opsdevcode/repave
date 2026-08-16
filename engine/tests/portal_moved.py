"""Shared assertions for HTML surfaces that now point at Backstage."""

from __future__ import annotations


def assert_surface_moved(response, surface_id: str) -> None:
    assert response.status_code == 200
    assert f'data-surface-moved="{surface_id}"' in response.text
    assert "CLI and" in response.text
    assert "/api/v2" in response.text
