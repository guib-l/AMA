"""Shared fixtures of the AMAC tests."""

import pytest

from amac.config import CONFIG_ENV, clear_config_cache


@pytest.fixture(autouse=True)
def isolated_config(tmp_path_factory, monkeypatch):
    """Never read the configuration file of the user running the tests."""
    monkeypatch.delenv(CONFIG_ENV, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path_factory.mktemp("xdg")))
    clear_config_cache()
    yield
    clear_config_cache()
