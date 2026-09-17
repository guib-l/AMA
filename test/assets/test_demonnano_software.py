"""Tests of the deMonNano software with a fake ``deMonPy`` library.

No deMonNano installation is involved: the library and the binary are created by
the tests, as ``amac_dummy_lib`` is for the dummy software.
"""

import importlib
import sys

import pytest
from ase.build import molecule
from ase.units import Hartree

from amac import AMAC
from amac.assets import demonnano as handlers
from amac.assets.demonnano.demonnano import (
    ACTIVE,
    BASIS,
    CALCULATOR_KEY,
    MODULES,
    PARAMETERS,
    DeMonNano,
)
from amac.engine.context import OUTPUT_KEY, RunContext
from amac.exceptions import (
    ConfigurationError,
    ExecutableNotFoundError,
    ValidationError,
)
from amac.parameter.composer import translate
from amac.parameter.parameters import CalculationSpec, ExecutionSpec

ENERGY = -4.0710651894

# Excerpts of the files the program writes, as in test_demonnano_parser.
OUT = """\
 deMonNano, DFTB calculation

 DFTB band energy                     :       -2.5600000000
 DFTB total energy                    :       -4.0710651894

                    CARTESIAN GRADIENT
    1 O      0.00100000     0.00200000    -0.00300000
    2 H     -0.00050000     0.00000000     0.00150000
    3 H     -0.00050000    -0.00200000     0.00150000

 charge dipole    =   0.000000   0.730000   0.000000
"""

MOL = """\
3
 step 1 -4.0710651894
O    0.0000000    0.0100000    0.0000000   -0.6200000
H    0.7600000    0.5900000    0.0000000    0.3100000
H   -0.7600000    0.5900000    0.0000000    0.3100000
"""

PACKAGE = '"""Fake deMonPy."""\n__version__ = "0.1.1"\n'
LIBRARY = f'''\
"""Fake deMonPy.deMonNano: writes the files the real program would write."""

from pathlib import Path

OUT = """{OUT}"""
MOL = """{MOL}"""


class deMonNano:
    def __init__(
        self, execut=None, workdir=".", omp_threads=1, properties=None, **parameters
    ):
        self.execut = execut
        self.workdir = Path(workdir)
        self.omp_threads = omp_threads
        self.properties = properties
        self.parameters = parameters
        self.calls = []
        self.results = {{}}

    def calculate(self, *, symbols, positions, read_charges=False, **kwargs):
        self.calls.append(("calculate", list(symbols), read_charges))
        (self.workdir / "deMon.out").write_text(OUT, encoding="utf-8")
        (self.workdir / "deMon.mol").write_text(MOL, encoding="utf-8")
        self.results = {{"energy": {{"energy": {ENERGY}}}, "converged": True}}


class Module_DeMonNano(deMonNano):
    def __init__(self, module=None, **kwargs):
        super().__init__(**kwargs)
        self.module = module

    def __call__(self, **kwds):
        image = kwds.pop("image")
        self.calls.append(("module", self.module, kwds))
        self.calculate(symbols=list(image.symbols), positions=image.get_positions())
'''

SPEC = {
    "method": "DFTB",
    "method_args": {"variant": "DFTB2"},
    "parameters": {"SLATER_KOSTER_FILES": {"SKFILE": "sk-files"}},
}


@pytest.fixture(autouse=True)
def clean_modules(monkeypatch):
    """Hide any real library and remove the fake one after each test."""
    monkeypatch.delenv("DEMON_EXECUTABLE", raising=False)
    yield
    for name in [n for n in sys.modules if n == "deMonPy" or n.startswith("deMonPy.")]:
        sys.modules.pop(name, None)
    importlib.invalidate_caches()


@pytest.fixture
def fake_library(tmp_path, monkeypatch):
    """Install the fake ``deMonPy`` package on the import path."""
    package = tmp_path / "site" / "deMonPy"
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text(PACKAGE, encoding="utf-8")
    (package / "deMonNano.py").write_text(LIBRARY, encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path / "site"))
    sys.modules.pop("deMonPy", None)
    importlib.invalidate_caches()


@pytest.fixture
def executable(tmp_path):
    """Create a file that passes the executable check of AMAC."""
    path = tmp_path / "deMon.x"
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(0o755)
    return path


def make_ctx(tmp_path, executable=None, **overrides) -> RunContext:
    """Return a context ready for ``build``, as ``AMAC`` would build it."""
    arguments = {**SPEC, **overrides}
    spec = CalculationSpec.from_kwargs(
        arguments["method"],
        arguments["method_args"],
        arguments.get("module", "SINGLE_POINT"),
        arguments.get("module_args", {}),
        arguments["parameters"],
        arguments.get("raw"),
    )
    exec_spec = ExecutionSpec(
        executable=None if executable is None else str(executable), cpu=4
    )
    directory = tmp_path / "run"
    directory.mkdir(exist_ok=True)
    software = DeMonNano()
    ctx = RunContext(molecule("H2O"), spec, exec_spec, directory, software=software)
    ctx.metadata["input_tree"] = translate(spec, software.schema())
    return ctx


def module_call(ctx) -> dict:
    """Return the keyword arguments the module of the library received."""
    _, _, kwds = ctx.objects[CALCULATOR_KEY].calls[0]
    return kwds


def test_class_attributes():
    assert (DeMonNano.NAME, DeMonNano.ALIASES) == ("DEMON", ("deMonNano",))
    assert DeMonNano.EXECUTION == "INPROCESS"
    # The library starts deMon.x: a run still needs an explicit executable.
    assert DeMonNano.REQUIRES_EXECUTABLE is True
    assert DeMonNano.EXECUTABLE_ENV == "DEMON_EXECUTABLE"


def test_check_environment_without_the_library(monkeypatch):
    monkeypatch.setitem(sys.modules, "deMonPy", None)
    with pytest.raises(ConfigurationError, match="deMonPy"):
        DeMonNano().check_environment()


def test_check_environment_with_the_library(fake_library):
    assert DeMonNano().check_environment() is None


def test_build_gives_the_library_its_arguments(tmp_path, executable, fake_library):
    ctx = make_ctx(tmp_path, executable)
    ctx.software.build(ctx)
    calculator = ctx.objects[CALCULATOR_KEY]
    assert calculator.execut == str(executable)
    assert calculator.workdir == ctx.directory
    assert calculator.omp_threads == 4
    assert calculator.parameters[BASIS] == {"SKFILE": "sk-files"}
    assert calculator.parameters[PARAMETERS][ACTIVE]["DFTB"] == {"SCC": True}
    assert MODULES not in calculator.parameters


def test_build_injects_the_ci_block(tmp_path, executable, fake_library):
    ctx = make_ctx(tmp_path, executable, method_args={"variant": "DFTB-CI"})
    ctx.software.build(ctx)
    active = ctx.objects[CALCULATOR_KEY].parameters[PARAMETERS][ACTIVE]
    # The CI block is what switches the CI on, even without any argument.
    assert active["CI"] == {}
    assert active["DFTB"] == {"SCC": True}


def test_build_keeps_the_ci_arguments(tmp_path, executable, fake_library):
    ctx = make_ctx(
        tmp_path, executable, method_args={"variant": "CI-DFTB", "SIZECI": 4}
    )
    ctx.software.build(ctx)
    active = ctx.objects[CALCULATOR_KEY].parameters[PARAMETERS][ACTIVE]
    assert active["CI"] == {"SIZECI": 4}


def test_build_completes_the_dynamics(tmp_path, executable, fake_library):
    ctx = make_ctx(
        tmp_path,
        executable,
        module="MD",
        module_args={"STEPS": 200, "THERMOSTAT": "NOSE"},
    )
    ctx.software.build(ctx)
    block = ctx.objects[CALCULATOR_KEY].parameters[MODULES][ACTIVE]["MD"]
    # The library pops these three without a default, and reads every thermostat.
    assert block["MDYNAMICS"] == {"RANDOM": 300}
    assert block["TIMESTEP"] == 0.4
    assert block["MDSTEP"] == {"MAX": 200, "OUT": 10}
    assert block["MDBATH"]["NOSE"] is True
    assert block["MDBATH"]["BERE"] is False


def test_build_writes_only_the_chosen_optimiser(tmp_path, executable, fake_library):
    ctx = make_ctx(
        tmp_path, executable, module="OPT", module_args={"ALGORITHM": "SDC", "MAX": 50}
    )
    ctx.software.build(ctx)
    block = ctx.objects[CALCULATOR_KEY].parameters[MODULES][ACTIVE]["OPT"]
    assert block == {"MAX": 50, "SDC": True}


def test_build_refuses_text_raw(tmp_path, executable, fake_library):
    ctx = make_ctx(tmp_path, executable, raw="PRINT MOE")
    with pytest.raises(ValidationError, match="raw keywords must be a mapping"):
        ctx.software.build(ctx)


def test_build_without_executable(tmp_path, fake_library):
    ctx = make_ctx(tmp_path)
    with pytest.raises(ExecutableNotFoundError, match="executable not found"):
        ctx.software.build(ctx)


def test_compute_single_point(tmp_path, executable, fake_library):
    ctx = make_ctx(tmp_path, executable)
    ctx.software.build(ctx)
    ctx.software.compute(ctx)
    calculator = ctx.objects[CALCULATOR_KEY]
    # A single point goes through the plain calculator, asking for the charges.
    assert type(calculator).__name__ == "deMonNano"
    assert calculator.calls == [("calculate", ["O", "H", "H"], True)]


def test_compute_optimisation(tmp_path, executable, fake_library):
    ctx = make_ctx(
        tmp_path,
        executable,
        module="OPT",
        module_args={"MAX": 50, "ALGORITHM": "SDC", "TOL": 0.0001},
    )
    ctx.software.build(ctx)
    ctx.software.compute(ctx)
    calculator = ctx.objects[CALCULATOR_KEY]
    assert calculator.module == "opt"
    # The module rewrites its own block: the values of the tree are passed again.
    assert module_call(ctx) == {"max": 50, "algo": "SDC", "out": 1, "TOL": 0.0001}
    assert calculator.calls[1] == ("calculate", ["O", "H", "H"], False)


def test_compute_dynamics(tmp_path, executable, fake_library):
    ctx = make_ctx(
        tmp_path,
        executable,
        module="MD",
        module_args={"TIMESTEP": 0.5, "STEPS": 200, "INITIAL_TEMPERATURE": 400},
    )
    ctx.software.build(ctx)
    ctx.software.compute(ctx)
    assert ctx.objects[CALCULATOR_KEY].module == "md"
    assert module_call(ctx) == {
        "temp": 400,
        "timestep": 0.5,
        "max_steps": 200,
        "out": 10,
        "out_traj": True,
    }


def test_collect_lists_files_and_normalizes(tmp_path, executable, fake_library):
    ctx = make_ctx(tmp_path, executable)
    ctx.software.build(ctx)
    ctx.software.compute(ctx)
    ctx.software.collect(ctx)
    assert sorted(ctx.files) == ["deMon.mol", "deMon.out"]
    output = ctx.objects[OUTPUT_KEY]
    assert output.energy == pytest.approx(ENERGY)
    # Only the library knows that the run converged.
    assert output.converged is True


def test_calculator_runs_and_handlers_convert(tmp_path, executable, fake_library):
    calc = AMAC(
        software="deMonNano",
        workdir=tmp_path / "work",
        label="water",
        executable=str(executable),
        **SPEC,
    )
    calc.handler_properties(handlers.energy, handlers.forces, handlers.charges)
    result = calc.execute(molecule("H2O"))
    assert result.success
    # Hartree -> eV, Hartree/Bohr -> eV/Angstrom, charges unchanged.
    assert result.properties["energy"] == pytest.approx(ENERGY * Hartree)
    assert result.properties["forces"].shape == (3, 3)
    assert result.properties["charges"] == pytest.approx([-0.62, 0.31, 0.31])
    assert result.provenance["software"] == "DEMON"
    assert result.provenance["driver"] == "amac"


def test_reprocess_without_the_library(tmp_path, executable, fake_library):
    calc = AMAC(
        software="DEMON",
        workdir=tmp_path / "work",
        label="water",
        executable=str(executable),
        keep_files=True,
        **SPEC,
    )
    calc.handler_properties(handlers.energy)
    calc.execute(molecule("H2O"))
    again = calc.reprocess(
        tmp_path / "work" / "water", [handlers.energy, handlers.charges]
    )
    assert again.properties["energy"] == pytest.approx(ENERGY * Hartree)
    assert again.properties["charges"] == pytest.approx([-0.62, 0.31, 0.31])
