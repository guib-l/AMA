"""Tests of the shared cclib driver with a fake ``cclib`` module."""

import importlib
import sys

import pytest
from ase import Atoms

from amac import AMAC
from amac.assets import _dummy
from amac.assets._dummy.dummy import OUTPUT_FILE, DummyOutput, DummySoftware
from amac.assets._shared.cclib_driver import CclibDriver
from amac.engine import registry
from amac.engine.context import OUTPUT_KEY
from amac.engine.registry import available_software, get_software
from amac.parameter.catalog import documented_software

SHARED = "amac.assets._shared"
PARAMETERS = {
    "method": "DFT",
    "method_args": {"variant": "PBE"},
    "parameters": {"BASIS": "sto-3g"},
}

CCLIB_IO = '''\
"""Fake cclib.io, reading the JSON output of the dummy program."""

import json
from pathlib import Path
from types import SimpleNamespace


def ccread(source):
    return SimpleNamespace(**json.loads(Path(source).read_text(encoding="utf-8")))
'''


class JsonCclibDriver(CclibDriver):
    OUTPUT_FILE = OUTPUT_FILE

    def to_output(self, data):
        return DummyOutput(data.energy, data.forces, data.method)


class CclibSoftware(DummySoftware):
    NAME = "CCLIB_DRIVER_TEST"
    DRIVERS = (JsonCclibDriver,)


def water() -> Atoms:
    positions = [[0.0, 0.0, 0.0], [0.76, 0.59, 0.0], [-0.76, 0.59, 0.0]]
    return Atoms("OH2", positions=positions)


def make_calc(tmp_path, **kwargs) -> AMAC:
    arguments = {
        "software": "cclib_driver_test",
        "driver": "cclib",
        "workdir": tmp_path / "work",
        "validate": "off",
    }
    calc = AMAC(**arguments | PARAMETERS | kwargs)
    calc.handler_properties(_dummy.energy)
    return calc


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """No executable variable during the test, no fake cclib left after it."""
    monkeypatch.delenv("DUMMY_EXECUTABLE", raising=False)
    monkeypatch.delenv("CCLIB_DRIVER_TEST_EXECUTABLE", raising=False)
    yield
    for name in list(sys.modules):
        if name.split(".")[0] == "cclib":
            del sys.modules[name]
    importlib.invalidate_caches()


@pytest.fixture
def fake_cclib(tmp_path, monkeypatch):
    """Make a fake cclib importable and register the test software."""
    package = tmp_path / "site" / "cclib"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("", encoding="utf-8")
    (package / "io.py").write_text(CCLIB_IO, encoding="utf-8")
    monkeypatch.syspath_prepend(str(package.parent))
    monkeypatch.setattr(registry, "_REGISTRY", dict(registry._REGISTRY))
    registry.register_software(CclibSoftware)


def test_driver_attributes_and_no_import():
    driver = CclibDriver()
    assert (driver.NAME, driver.REQUIRES, driver.DISTRIBUTION) == (
        "cclib",
        ("cclib",),
        "cclib",
    )
    assert driver.PHASES == frozenset({"collect"})
    assert driver.missing_modules() == ["cclib"]
    assert "cclib" not in sys.modules
    assert not any(
        get_software(name).__module__.startswith(SHARED)
        for name in available_software()
    )


def test_documented_software_ignores_shared():
    assert not any(
        get_software(name).__module__.startswith(SHARED)
        for name in documented_software()
    )


def test_to_output_is_implemented_by_subclasses():
    with pytest.raises(NotImplementedError, match="to_output"):
        CclibDriver().to_output(object())


def test_collect_fills_files_native_object_and_output(tmp_path, fake_cclib):
    result = make_calc(tmp_path).execute(water())

    ctx = result.context
    assert result.provenance["driver"] == "cclib"
    assert set(ctx.files) == {OUTPUT_FILE}
    assert ctx.objects["cclib"].energy == pytest.approx(-1.0, abs=1e-12)
    assert ctx.objects[OUTPUT_KEY] == DummyOutput(-1.0, [], "DFT")
    assert result.properties["energy"] == pytest.approx(-1.0, abs=1e-12)


def test_reprocess_reads_with_cclib(tmp_path, fake_cclib):
    calc = make_calc(tmp_path)
    directory = calc.execute(water()).context.directory

    again = calc.reprocess(directory)
    assert set(again.context.objects) == {"cclib", OUTPUT_KEY}
    assert again.properties["energy"] == pytest.approx(-1.0, abs=1e-12)


def test_unreadable_output_fails_collect(tmp_path, fake_cclib, monkeypatch):
    import cclib.io

    monkeypatch.setattr(cclib.io, "ccread", lambda source: None)
    result = make_calc(tmp_path, raise_on_error=False).execute(water())

    assert not result.success
    assert result.properties == {}
    assert "cclib could not read" in str(result.errors[0])
