"""Tests of the normalized output pattern with the dummy software and a fake library."""

import importlib
import sys

import pytest
from ase import Atoms

import amac
from amac import AMAC
from amac.assets import _dummy
from amac.assets._dummy.dummy import OUTPUT_FILE, DummyOutput, parse_directory
from amac.engine.context import OUTPUT_KEY, RunContext, cached_output
from amac.exceptions import HandlerError

PARAMETERS = {
    "method": "DFT",
    "method_args": {"variant": "PBE"},
    "parameters": {"BASIS": "sto-3g"},
}

LIBRARY = '''\
"""Fake dedicated library of the dummy software, created by the tests."""

import json
from pathlib import Path
from types import SimpleNamespace


def write_input(spec, directory):
    path = Path(directory) / "input.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def compute(directory, cpu=1):
    directory = Path(directory)
    spec = json.loads((directory / "input.json").read_text(encoding="utf-8"))
    result = {"energy": -2.0, "forces": [], "method": spec["method"]}
    (directory / "output.json").write_text(json.dumps(result), encoding="utf-8")


def read_output(directory):
    path = Path(directory) / "output.json"
    return SimpleNamespace(**json.loads(path.read_text(encoding="utf-8")))
'''


def water() -> Atoms:
    positions = [[0.0, 0.0, 0.0], [0.76, 0.59, 0.0], [-0.76, 0.59, 0.0]]
    return Atoms("OH2", positions=positions)


def make_calc(tmp_path, **kwargs) -> AMAC:
    arguments = {"software": "dummy", "workdir": tmp_path / "work", "validate": "off"}
    return AMAC(**arguments | PARAMETERS | kwargs)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """No executable variable during the test, no fake library left after it."""
    monkeypatch.delenv("DUMMY_EXECUTABLE", raising=False)
    yield
    sys.modules.pop("amac_dummy_lib", None)
    importlib.invalidate_caches()


@pytest.fixture
def dummy_lib(tmp_path, monkeypatch):
    """Make amac_dummy_lib importable from a temporary sys.path entry."""
    package = tmp_path / "site" / "amac_dummy_lib"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(LIBRARY, encoding="utf-8")
    monkeypatch.syspath_prepend(str(package.parent))


def test_cached_output_parses_once(tmp_path):
    calc = make_calc(tmp_path)
    ctx = RunContext(water(), calc.spec, calc.exec_spec, tmp_path)
    calls = []

    def parse(directory):
        calls.append(directory)
        return DummyOutput(-3.0, [], "DFT")

    first = cached_output(ctx, parse)
    assert first == DummyOutput(-3.0, [], "DFT")
    assert ctx.objects[OUTPUT_KEY] is first
    assert cached_output(ctx, parse) is first
    assert calls == [tmp_path]


def test_collecting_driver_fills_files_and_output(tmp_path, dummy_lib):
    calc = make_calc(tmp_path, driver="dummy-lib")
    calc.handler_properties(_dummy.energy, _dummy.forces)
    result = calc.execute(water())

    ctx = result.context
    assert set(ctx.files) == {OUTPUT_FILE}
    assert ctx.objects[OUTPUT_KEY] == DummyOutput(-2.0, [], "DFT")
    assert result.properties["energy"] == pytest.approx(-2.0, abs=1e-12)
    assert result.properties["forces"] == []


def test_requires_files_applies_to_the_output(tmp_path, dummy_lib):
    calc = make_calc(tmp_path, driver="dummy-lib")
    calc.handler_properties(_dummy.energy)
    directory = calc.execute(water()).context.directory
    (directory / OUTPUT_FILE).unlink()

    again = calc.reprocess(directory)
    assert again.success
    assert again.properties == {}
    assert OUTPUT_KEY not in again.context.objects
    [error] = again.errors
    assert isinstance(error, HandlerError)
    assert "missing files: output.json" in str(error)


def test_reprocess_through_the_driver(tmp_path, dummy_lib):
    calc = make_calc(tmp_path, driver="dummy-lib")
    calc.handler_properties(_dummy.energy)
    result = calc.execute(water())

    for again in (
        calc.reprocess(result.context.directory),
        amac.reprocess(result, [_dummy.energy]),
    ):
        assert again.context.driver == "dummy-lib"
        assert again.context.objects[OUTPUT_KEY] == DummyOutput(-2.0, [], "DFT")
        assert again.properties["energy"] == pytest.approx(-2.0, abs=1e-12)


def test_reprocess_rebuilds_the_output_from_the_files(tmp_path, dummy_lib):
    written = make_calc(tmp_path, driver="dummy-lib", label="lib")
    written.handler_properties(_dummy.native_energy)
    directory = written.execute(water()).context.directory
    calc = make_calc(tmp_path)

    again = calc.reprocess(directory, handlers=[_dummy.energy, _dummy.forces])
    assert again.context.objects == {OUTPUT_KEY: DummyOutput(-2.0, [], "DFT")}
    assert again.properties["energy"] == pytest.approx(-2.0, abs=1e-12)
    assert again.properties["forces"] == []
    assert parse_directory(directory) == DummyOutput(-2.0, [], "DFT")


def test_module_reprocess_rebuilds_the_output_from_the_files(tmp_path):
    calc = make_calc(tmp_path)
    calc.handler_properties(_dummy.forces)
    result = calc.execute(water())
    assert result.context.objects[OUTPUT_KEY] == DummyOutput(-1.0, [], "DFT")

    again = amac.reprocess(result, [_dummy.energy])
    assert again.context.objects == {OUTPUT_KEY: DummyOutput(-1.0, [], "DFT")}
    assert again.properties["energy"] == pytest.approx(-1.0, abs=1e-12)
