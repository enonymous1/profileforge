"""Shared pytest fixtures."""

from __future__ import annotations

import pytest

from profileforge.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> object:
    """Keep the cached settings from leaking between tests."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
