"""Shared Home Assistant fixtures for Nutri Points."""

from __future__ import annotations

import pytest

import custom_components


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable loading custom integrations in every test."""
    custom_components.__path__ = [
        path for path in custom_components.__path__ if not str(path).endswith(".__path_hook__")
    ]
