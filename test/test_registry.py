"""Tests of amac.engine.registry."""

import pytest

from amac.assets._dummy.dummy import DummySoftware
from amac.assets._dummy.inprocess import DummyInProcess
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
        ("DUMMY", DummySoftware),
        ("dummy", DummySoftware),
        ("DuMmY", DummySoftware),
        ("DUMMY_INPROCESS", DummyInProcess),
        ("Dummy-InProcess", DummyInProcess),
    ],
)
def test_get_software(name, expected):
    assert get_software(name) is expected


def test_unknown_software():
    with pytest.raises(SoftwareNotFoundError, match="Unknown software 'NOPE'.*DUMMY"):
        get_software("NOPE")


def test_software_name_must_be_str():
    with pytest.raises(TypeError, match="str"):
        get_software(42)


def test_available_software_lists_canonical_names():
    names = available_software()
    assert names == sorted(names)
    known = {"DUMMY", "DUMMY_INPROCESS", "ORCA", "GAUSSIAN", "DFTBP", "DEMON"}
    assert known <= set(names)
    assert "DUMMY-INPROCESS" not in names


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
    [("dummy", ()), ("CLASH_TEST", ("DUMMY-INPROCESS",))],
    ids=["name", "alias"],
)
def test_duplicate_names_are_refused(name, aliases):
    class ClashSoftware(FileIOSoftware):
        NAME = name
        ALIASES = aliases

        def command(self, ctx):
            return []

    with pytest.raises(ValueError, match="already registered by Dummy"):
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
    assert DummySoftware().name == "DUMMY"
