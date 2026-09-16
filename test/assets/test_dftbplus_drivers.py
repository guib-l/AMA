"""Tests of the DFTB+ drivers with fake ``hsd`` and ``dftbplus`` modules.

No DFTB+ installation is involved: both libraries are created by the tests, as
``amac_dummy_lib`` is for the dummy software.
"""

import importlib
import sys

import pytest
from ase.build import molecule

from amac.assets.dftbplus.drivers import LIBRARY_ENV, DftbPlusApiDriver, HsdDriver
from amac.assets.dftbplus.dftbplus import DftbPlus
from amac.engine.context import OUTPUT_KEY, RunContext
from amac.parameter.composer import inject_resources, translate
from amac.parameter.parameters import CalculationSpec, ExecutionSpec
from amac.parameter.schema import load

HSD = '''\
"""Fake hsd-python: writes the nested dict as indented blocks."""


def dump_string(data, indent=0):
    lines = []
    for name, value in data.items():
        pad = "  " * indent
        if isinstance(value, dict):
            lines.append(f"{pad}{name} = {{")
            lines.append(dump_string(value, indent + 1))
            lines.append(f"{pad}}}")
        else:
            lines.append(f"{pad}{name} = {value}")
    return "\\n".join(lines) + ("\\n" if indent == 0 else "")
'''

DFTBPLUS = '''\
"""Fake DFTB+ Python API: writes the files the real program would write."""

from pathlib import Path


class DftbPlus:
    def __init__(self, libpath, hsdpath, logfile):
        self.libpath = libpath
        self.directory = Path(hsdpath).parent
        Path(logfile).write_text("fake dftb+ log\\n", encoding="utf-8")
        self.geometry = None

    def set_geometry(self, positions, latvecs=None):
        self.geometry = (positions, latvecs)

    def get_energy(self):
        (self.directory / "results.tag").write_text(
            "total_energy         :real:0:\\n -0.250000000000E+001\\n", encoding="utf-8"
        )
        (self.directory / "detailed.out").write_text(
            " Total energy:  -2.5000000000 H\\n", encoding="utf-8"
        )
        return -2.5

    def close(self):
        self.closed = True
'''


def water():
    return molecule("H2O")


def make_spec() -> CalculationSpec:
    return CalculationSpec.from_kwargs(
        method="TIGHT_BINDING",
        method_args={"variant": "DFTB2", "MaxAngularMomentum": {"O": "p", "H": "s"}},
        parameters={
            "SLATER_KOSTER_FILES": {"variant": "Type2FileNames", "Prefix": "mio"}
        },
    )


def make_ctx(directory, exec_spec=None) -> RunContext:
    spec = make_spec()
    exec_spec = exec_spec or ExecutionSpec()
    schema = load(DftbPlus.DOC)
    ctx = RunContext(water(), spec, exec_spec, directory, software=DftbPlus())
    tree = translate(spec, schema)
    inject_resources(tree, schema, exec_spec)
    ctx.metadata["input_tree"] = tree
    return ctx


@pytest.fixture(autouse=True)
def clean_modules(monkeypatch):
    """Remove the fake libraries after each test."""
    monkeypatch.delenv(LIBRARY_ENV, raising=False)
    yield
    for name in ("hsd", "dftbplus"):
        sys.modules.pop(name, None)
    importlib.invalidate_caches()


@pytest.fixture
def fake_hsd(tmp_path, monkeypatch):
    (tmp_path / "site").mkdir(exist_ok=True)
    (tmp_path / "site" / "hsd.py").write_text(HSD, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path / "site"))


@pytest.fixture
def fake_api(tmp_path, monkeypatch):
    (tmp_path / "site").mkdir(exist_ok=True)
    (tmp_path / "site" / "dftbplus.py").write_text(DFTBPLUS, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path / "site"))


def test_driver_attributes_and_no_import():
    assert (HsdDriver.NAME, HsdDriver.PHASES) == ("hsd", frozenset({"prepare"}))
    assert HsdDriver.SUPPORTS_RAW is True
    assert HsdDriver().missing_modules() == ["hsd"]
    assert DftbPlusApiDriver.PHASES == frozenset({"run", "collect"})
    assert DftbPlusApiDriver().missing_modules() == ["dftbplus"]
    assert (DftbPlus.DRIVERS[0], DftbPlus.DRIVERS[1]) == (DftbPlusApiDriver, HsdDriver)
    assert "hsd" not in sys.modules and "dftbplus" not in sys.modules


def test_hsd_driver_writes_the_geometry_and_the_tree(tmp_path, fake_hsd):
    directory = tmp_path / "run"
    directory.mkdir()
    ctx = make_ctx(directory)
    HsdDriver().prepare(DftbPlus(), ctx)

    assert set(ctx.input_files) == {"dftb_in.hsd"}
    text = ctx.input_files["dftb_in.hsd"].read_text(encoding="utf-8")
    assert text.startswith("Geometry = GenFormat {")
    assert "O" in text and "H" in text
    assert "Hamiltonian = {" in text
    assert "SCC = True" in text  # The fake library does not render booleans.
    # WriteResultsTag is written by the driver too, through complete_tree.
    assert "WriteResultsTag = True" in text


def test_hsd_driver_applies_raw(tmp_path, fake_hsd):
    directory = tmp_path / "raw"
    directory.mkdir()
    ctx = make_ctx(directory)
    ctx.metadata["input_tree"].raw = {"ParserOptions": {"StopAfterParsing": True}}
    HsdDriver().prepare(DftbPlus(), ctx)

    text = ctx.input_files["dftb_in.hsd"].read_text(encoding="utf-8")
    assert "StopAfterParsing = True" in text


def test_hsd_driver_writes_raw_text_at_the_end(tmp_path, fake_hsd):
    directory = tmp_path / "raw-text"
    directory.mkdir()
    ctx = make_ctx(directory)
    ctx.metadata["input_tree"].raw = ["# added as-is"]
    HsdDriver().prepare(DftbPlus(), ctx)

    text = ctx.input_files["dftb_in.hsd"].read_text(encoding="utf-8")
    assert text.rstrip().endswith("# added as-is")


def test_hsd_driver_keeps_a_raw_geometry(tmp_path, fake_hsd):
    directory = tmp_path / "raw-geometry"
    directory.mkdir()
    ctx = make_ctx(directory)
    ctx.metadata["input_tree"].raw = {"Geometry": {"xyzFormat": "geo.xyz"}}
    HsdDriver().prepare(DftbPlus(), ctx)

    text = ctx.input_files["dftb_in.hsd"].read_text(encoding="utf-8")
    assert "GenFormat" not in text
    assert "xyzFormat = geo.xyz" in text


def test_hsd_driver_needs_a_tree(tmp_path, fake_hsd):
    ctx = make_ctx(tmp_path)
    ctx.metadata.clear()
    with pytest.raises(ValueError, match="no input tree"):
        HsdDriver().prepare(DftbPlus(), ctx)


def test_api_driver_refuses_an_unset_library():
    reason = DftbPlusApiDriver().check_environment(DftbPlus())
    assert reason is not None and LIBRARY_ENV in reason


def test_api_driver_accepts_the_library_of_the_environment(monkeypatch):
    monkeypatch.setenv(LIBRARY_ENV, "/opt/dftbplus/lib/libdftbplus.so")
    driver = DftbPlusApiDriver()
    assert driver.check_environment(DftbPlus()) is None
    assert driver.library_path(DftbPlus()) == "/opt/dftbplus/lib/libdftbplus.so"


def test_api_driver_runs_and_collects(tmp_path, fake_api, monkeypatch):
    monkeypatch.setenv("OMP_NUM_THREADS", "1")
    directory = tmp_path / "run"
    directory.mkdir()
    library = str(tmp_path / "libdftbplus.so")
    exec_spec = ExecutionSpec(cpu=4, env={LIBRARY_ENV: library})
    ctx = make_ctx(directory, exec_spec)
    software = DftbPlus()
    driver = DftbPlusApiDriver()

    driver.run(software, ctx)
    assert ctx.objects["dftbplus"].libpath == library
    assert ctx.objects["energy"] == pytest.approx(-2.5)
    assert ctx.return_code == 0
    assert (directory / "dftb.out").is_file()

    driver.collect(software, ctx)
    assert {"results.tag", "detailed.out", "dftb.out"} <= set(ctx.files)
    assert ctx.objects[OUTPUT_KEY].energy == pytest.approx(-2.5)
