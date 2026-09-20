"""Tests of amac.engine.registry.

The registered software are the real ones (``DFTBP``, ``DEMON``); the registration
rules themselves are checked on throw-away classes declared here, registered in a
copy of the global registry.
"""

import importlib

import pytest

from amac.assets.demonnano.demonnano import DeMonNano
from amac.assets.dftbplus.dftbplus import DftbPlus
from amac.engine import registry
from amac.engine.registry import available_software, get_software, register_software
from amac.engine.software import FileIOSoftware, Software
from amac.exceptions import SoftwareNotFoundError


@pytest.fixture(autouse=True)
def isolated_registry(monkeypatch):
    """Register test software in a copy of the global registry."""
    monkeypatch.setattr(registry, "_REGISTRY", dict(registry._REGISTRY))


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("DFTBP", DftbPlus),
        ("dftbp", DftbPlus),
        ("DfTbP", DftbPlus),
        ("DFTB+", DftbPlus),
        ("dftb+", DftbPlus),
        ("DEMON", DeMonNano),
        ("deMonNano", DeMonNano),
    ],
)
def test_get_software(name, expected):
    assert get_software(name) is expected


def test_unknown_software():
    with pytest.raises(SoftwareNotFoundError, match="Unknown software 'NOPE'.*DFTBP"):
        get_software("NOPE")


def test_software_name_must_be_str():
    with pytest.raises(TypeError, match="str"):
        get_software(42)


def test_available_software_lists_canonical_names():
    names = available_software()
    assert names == sorted(names)
    assert {"DFTBP", "DEMON"} <= set(names)
    assert "DFTB+" not in names  # Aliases are not canonical names.


def test_register_with_aliases():
    class ToolSoftware(FileIOSoftware):
        NAME = "TOOL_TEST"
        ALIASES = ("tool", "Tool-Alias")

        def command(self, ctx):
            return []

    assert register_software(ToolSoftware) is ToolSoftware
    assert register_software(ToolSoftware) is ToolSoftware
    assert get_software("tool-alias") is get_software("TOOL") is ToolSoftware
    assert "TOOL_TEST" in available_software()


@pytest.mark.parametrize(
    ("name", "aliases"),
    [("dftbp", ()), ("CLASH_TEST", ("DFTB+",))],
    ids=["name", "alias"],
)
def test_duplicate_names_are_refused(name, aliases):
    class ClashSoftware(FileIOSoftware):
        NAME = name
        ALIASES = aliases

        def command(self, ctx):
            return []

    with pytest.raises(ValueError, match="already registered by DftbPlus"):
        register_software(ClashSoftware)


def test_invalid_classes_are_refused():
    class IncompleteSoftware(FileIOSoftware):
        NAME = "INCOMPLETE_TEST"

    class NamelessSoftware(FileIOSoftware):
        def command(self, ctx):
            return []

    with pytest.raises(TypeError, match="abstract"):
        register_software(IncompleteSoftware)
    with pytest.raises(TypeError, match="non-empty"):
        register_software(NamelessSoftware)
    for cls in (Software, object):
        with pytest.raises(TypeError, match="not a subclass of Software"):
            register_software(cls)


def test_incomplete_software_cannot_be_instantiated():
    class IncompleteSoftware(FileIOSoftware):
        NAME = "INCOMPLETE_TEST"

    with pytest.raises(TypeError, match="abstract"):
        IncompleteSoftware()
    assert DftbPlus().name == "DFTBP"


def test_software_packages_are_lowercase():
    """Each software lives in a package named after it, in lowercase."""
    for name in ("dftbplus", "demonnano"):
        package = importlib.import_module(f"amac.assets.{name}")
        assert f"from amac.assets import {name}" in package.__doc__
    assert get_software("DFTB+").DOC.parent.name == "dftbplus"
