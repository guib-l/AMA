"""Tests of the optional library drivers, on DFTB+ with a fake library.

The drivers of ``amac.engine.drivers`` are generic, so the ones exercised here are
declared in this module and attached to :class:`DftbPlus` for the duration of a
test. The library they need, ``amac_fake_lib``, is written by the tests: no DFTB+
installation and no real driver library is involved. The drivers shipped with the
DFTB+ asset are tested in ``test/assets/test_dftbplus_drivers.py``.
"""

import importlib
import subprocess
import sys
import warnings
from pathlib import Path

import pytest
from ase import Atoms
from ase.units import Hartree
from conftest import STUB_ENERGY

import amac
from amac.assets import dftbplus
from amac.assets.dftbplus.dftbplus import DftbPlus
from amac.assets.dftbplus.parser import DETAILED_OUT, DftbPlusOutput
from amac.engine.context import OUTPUT_KEY
from amac.engine.drivers import (
    Driver,
    DriverSelection,
    select_driver,
    validate_driver_name,
)
from amac.engine.handlers import handler
from amac.exceptions import DriverUnavailableError, RunError, ValidationError

ROOT = Path(__file__).resolve().parents[1]
FAKE_MODULES = ("amac_fake_lib", "amac_probe_pkg")
FALLBACK = "fake-lib: missing Python module amac_fake_lib (pip install amac-fake-lib)"
# Energy the fake library writes, in Hartree; the stub program writes another one.
LIBRARY_ENERGY = -2.5

LIBRARY = '''\
"""Fake dedicated library of DFTB+, created by the tests."""

import json
from pathlib import Path


class Output:
    def __init__(self, energy, cpu):
        self.energy = energy
        self.cpu = cpu


def write_input(spec, directory):
    path = Path(directory) / "dftb_in.hsd"
    path.write_text(json.dumps(spec, sort_keys=True), encoding="utf-8")
    return path


def compute(directory, cpu=1):
    directory = Path(directory)
    text = " Total energy:  -2.5000000000 H\\n Used cores: %d\\n" % cpu
    (directory / "detailed.out").write_text(text, encoding="utf-8")


def read_output(directory):
    text = (Path(directory) / "detailed.out").read_text(encoding="utf-8")
    energy = float(text.split("Total energy:")[1].split("H")[0])
    # Another program may have written the file: the core count is then absent.
    cores = text.split("Used cores:")[1].split() if "Used cores:" in text else None
    return Output(energy, int(cores[0]) if cores else None)
'''


class FakeLibraryDriver(Driver):
    """Driver doing the three phases with ``amac_fake_lib``."""

    NAME = "fake-lib"
    REQUIRES = ("amac_fake_lib",)
    DISTRIBUTION = "amac-fake-lib"
    PHASES = frozenset({"prepare", "run", "collect"})
    # The library takes the core count and passes the environment to the program.
    SUPPORTED_SETTINGS = frozenset({"cpu", "env"})

    def prepare(self, software, ctx):
        import amac_fake_lib

        path = Path(amac_fake_lib.write_input(ctx.spec.to_dict(), ctx.directory))
        ctx.input_files[path.name] = path

    def run(self, software, ctx):
        import amac_fake_lib

        settings = self.execution_settings(software, ctx.exec_spec)
        amac_fake_lib.compute(ctx.directory, cpu=settings["cpu"])

    def collect(self, software, ctx):
        import amac_fake_lib

        path = ctx.directory / DETAILED_OUT
        if path.is_file():
            ctx.files[DETAILED_OUT] = path
            native = amac_fake_lib.read_output(ctx.directory)
            ctx.objects["fake_lib"] = native
            ctx.objects[OUTPUT_KEY] = DftbPlusOutput(energy=native.energy)


class CollectOnlyDriver(FakeLibraryDriver):
    """Driver leaving ``prepare`` and ``run`` to AMAC."""

    NAME = "fake-lib-collect"
    PHASES = frozenset({"collect"})


class PickyDriver(FakeLibraryDriver):
    """Driver refusing the environment it is offered."""

    NAME = "picky"

    def check_environment(self, software):
        return f"{software.name} is too old"


def water() -> Atoms:
    positions = [[0.0, 0.0, 0.0], [0.76, 0.59, 0.0], [-0.76, 0.59, 0.0]]
    return Atoms("OH2", positions=positions)


@pytest.fixture(autouse=True)
def clean_modules():
    """Leave no fake module behind after the test."""
    yield
    for name in list(sys.modules):
        if name.split(".")[0] in FAKE_MODULES:
            del sys.modules[name]
    importlib.invalidate_caches()


@pytest.fixture
def fake_lib(tmp_path, monkeypatch):
    """Make amac_fake_lib 1.2.3 importable from a temporary sys.path entry."""
    site = tmp_path / "site"
    (site / "amac_fake_lib").mkdir(parents=True)
    (site / "amac_fake_lib" / "__init__.py").write_text(LIBRARY, encoding="utf-8")
    metadata = site / "amac_fake_lib-1.2.3.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: amac-fake-lib\nVersion: 1.2.3\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(site))
    return site


@pytest.fixture
def fake_drivers(monkeypatch):
    """Return a factory replacing the drivers DFTB+ declares, for one test."""

    def use(*drivers):
        monkeypatch.setattr(DftbPlus, "DRIVERS", tuple(drivers))

    use(FakeLibraryDriver)
    return use


@pytest.mark.parametrize(
    ("attributes", "match"),
    [
        ({"NAME": "", "PHASES": {"collect"}}, "NAME"),
        ({"NAME": "Auto", "PHASES": {"collect"}}, "NAME"),
        ({"NAME": "bad", "REQUIRES": "module"}, "REQUIRES"),
        ({"NAME": "bad", "PHASES": set()}, "PHASES"),
        ({"NAME": "bad", "PHASES": {"deploy"}}, "PHASES"),
        ({"NAME": "bad", "PHASES": {"run"}}, "does not implement: run"),
        (
            {"NAME": "bad", "PHASES": {"collect"}, "SUPPORTED_SETTINGS": {"gpu"}},
            "SUPPORTED_SETTINGS",
        ),
    ],
)
def test_driver_subclasses_are_checked(attributes, match):
    namespace = {"collect": lambda self, software, ctx: None} | attributes
    with pytest.raises(TypeError, match=match):
        type("BadDriver", (Driver,), namespace)


def test_is_available_does_not_import(fake_lib):
    probe = fake_lib / "amac_probe_pkg"
    probe.mkdir()
    (probe / "__init__.py").write_text('raise ImportError("imported")\n', "utf-8")
    (probe / "sub.py").write_text("", encoding="utf-8")
    importlib.invalidate_caches()

    class ProbeDriver(FakeLibraryDriver):
        NAME = "probe"
        REQUIRES = ("amac_probe_pkg.sub",)

    class AbsentDriver(FakeLibraryDriver):
        NAME = "absent"
        REQUIRES = ("amac_probe_pkg.absent", "amac_absent_lib")

    assert FakeLibraryDriver().is_available()
    assert ProbeDriver().is_available()
    assert AbsentDriver().missing_modules() == [
        "amac_probe_pkg.absent",
        "amac_absent_lib",
    ]
    assert FakeLibraryDriver().version() == "1.2.3"
    assert not set(FAKE_MODULES) & sys.modules.keys()


def test_driver_without_library():
    driver = FakeLibraryDriver()
    assert not driver.is_available()
    assert driver.version() is None


def test_select_driver_names():
    """The names offered are those of the drivers the software declares."""
    assert select_driver(DftbPlus, "AMAC") == DriverSelection()
    unknown = "'opi' for DFTBP. Available: amac, auto, dftbplus-api, hsd"
    with pytest.raises(ValueError, match=unknown):
        select_driver(DftbPlus, "opi")
    with pytest.raises(TypeError, match="driver must be a str"):
        select_driver(DftbPlus, None)
    validate_driver_name(DftbPlus, "HSD")
    with pytest.raises(ValueError, match="Available"):
        validate_driver_name(DftbPlus, "opi")


def test_explicit_driver_available(tmp_path, fake_lib, fake_drivers, stub_calc):
    calc = stub_calc(driver="Fake-Lib", cpu=2, executable=None)
    assert (calc.driver.name, calc.driver.fallback) == ("fake-lib", None)
    assert isinstance(calc.driver.driver, FakeLibraryDriver)
    calc.handler_properties(dftbplus.energy)
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        result = calc.execute(water())

    assert (result.success, result.errors) == (True, [])
    assert result.properties["energy"] == pytest.approx(LIBRARY_ENERGY * Hartree)
    ctx = result.context
    assert (ctx.driver, ctx.stdout) == ("fake-lib", None)
    assert (set(ctx.input_files), set(ctx.files)) == ({"dftb_in.hsd"}, {DETAILED_OUT})
    assert ctx.objects["fake_lib"].cpu == 2
    assert calc.to_dict()["exec_spec"]["driver"] == "Fake-Lib"

    [loaded] = amac.load(calc.store(tmp_path / "driver"))
    provenance = loaded.provenance
    assert provenance["driver"] == "fake-lib"
    assert provenance["driver_version"] == "1.2.3"
    assert provenance["driver_fallback"] is None


def test_explicit_driver_unavailable(fake_drivers, stub_calc):
    with pytest.raises(DriverUnavailableError, match="pip install amac-fake-lib"):
        stub_calc(driver="fake-lib")
    with pytest.raises(ValueError, match="Available: amac, auto, fake-lib"):
        stub_calc(driver="opi")


def test_default_driver_is_amac(fake_lib, fake_drivers, stub_calc):
    """An available library changes nothing without ``driver=``."""
    calc = stub_calc()
    assert calc.driver == DriverSelection()
    calc.handler_properties(dftbplus.energy)
    result = calc.execute(water())
    assert result.properties["energy"] == pytest.approx(STUB_ENERGY * Hartree)


def test_auto_without_library(fake_drivers, stub_calc):
    calc = stub_calc(driver="auto")
    assert (calc.driver.name, calc.driver.fallback) == ("amac", FALLBACK)
    calc.handler_properties(dftbplus.energy)
    result = calc.execute(water())
    assert result.properties["energy"] == pytest.approx(STUB_ENERGY * Hartree)
    provenance = result.provenance
    assert (provenance["driver"], provenance["driver_version"]) == ("amac", None)
    assert provenance["driver_fallback"] == FALLBACK


def test_auto_with_library(fake_lib, fake_drivers, stub_calc):
    calc = stub_calc(driver="auto", executable=None)
    assert (calc.driver.name, calc.driver.fallback) == ("fake-lib", None)
    calc.handler_properties(dftbplus.energy)
    result = calc.execute(water())
    assert result.properties["energy"] == pytest.approx(LIBRARY_ENERGY * Hartree)
    provenance = result.provenance
    assert provenance["driver"] == "fake-lib"
    assert provenance["driver_version"] == "1.2.3"
    assert calc.to_dict()["exec_spec"]["driver"] == "auto"


def test_collect_only_driver(fake_lib, fake_drivers, stub_calc):
    """AMAC prepares and runs the program; the driver only reads what it wrote."""
    fake_drivers(CollectOnlyDriver)
    calc = stub_calc(driver="fake-lib-collect", ram=1000)
    calc.handler_properties(dftbplus.energy)
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        result = calc.execute(water())

    ctx = result.context
    # The stub program ran, so the energy is its own, read back by the driver.
    assert result.properties["energy"] == pytest.approx(STUB_ENERGY * Hartree)
    assert set(ctx.input_files) == {"dftb_in.hsd"}
    assert ctx.objects["fake_lib"].energy == pytest.approx(STUB_ENERGY)
    assert set(ctx.files) == {DETAILED_OUT}


def test_check_environment_failure(fake_lib, fake_drivers, stub_calc):
    fake_drivers(PickyDriver, FakeLibraryDriver)
    with pytest.raises(DriverUnavailableError, match="DFTBP is too old"):
        stub_calc(driver="picky")
    auto = stub_calc(driver="auto")
    assert (auto.driver.name, auto.driver.fallback) == ("fake-lib", None)

    fake_drivers(PickyDriver)
    fallback = stub_calc(driver="auto").driver
    assert (fallback.name, fallback.fallback) == ("amac", "picky: DFTBP is too old")


def test_handler_drivers_are_checked_against_the_selected_driver(
    fake_drivers, stub_calc, monkeypatch
):
    monkeypatch.setattr(DftbPlus, "HANDLERS", dict(DftbPlus.HANDLERS))

    @handler(software="DFTBP", drivers=("fake-lib",))
    def native_energy(ctx):
        return ctx.objects["fake_lib"].energy

    with pytest.raises(ValueError, match="driver 'amac'; compatible: fake-lib"):
        stub_calc().handler_properties(native_energy)
    auto = stub_calc(driver="auto")
    with pytest.raises(ValueError, match="fell back to it: fake-lib: missing"):
        auto.handler_properties(native_energy)


def test_raw_needs_driver_support(fake_lib, fake_drivers, stub_calc):
    raw = {"ParserOptions": {"ParserVersion": 14}}
    with pytest.raises(ValidationError, match="does not support raw keywords"):
        stub_calc(driver="fake-lib", raw=raw)
    auto = stub_calc(driver="auto", raw=raw)
    assert (auto.driver.name, auto.driver.fallback) == (
        "amac",
        "fake-lib: does not support raw keywords",
    )


def test_driver_phase_failure_is_a_failed_run(
    tmp_path, fake_lib, fake_drivers, stub_calc, monkeypatch
):
    import amac_fake_lib

    calls = []

    def crash(directory, cpu=1):
        calls.append(directory)
        raise RuntimeError("library crashed")

    monkeypatch.setattr(amac_fake_lib, "compute", crash)
    calc = stub_calc(driver="fake-lib", executable=None)
    calc.handler_properties(dftbplus.energy)
    with pytest.raises(RunError, match="library crashed") as excinfo:
        calc.execute(water())
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert excinfo.value.ctx.driver == "fake-lib"
    assert (excinfo.value.ctx.stdout, excinfo.value.ctx.files) == (None, {})

    calc = stub_calc(driver="fake-lib", raise_on_error=False, label="kept", executable=None)
    calc.handler_properties(dftbplus.energy)
    result = calc.execute(water())
    assert (result.success, result.properties) == (False, {})
    assert isinstance(result.errors[0], RunError)
    assert (result.context.stdout, result.context.return_code) == (None, None)
    assert len(calls) == 2


def test_ignored_settings_warn_once_per_execute(fake_lib, fake_drivers, stub_calc):
    calc = stub_calc(driver="fake-lib", cpu=4, ram=1000, timeout=30.0, executable=None)
    calc.handler_properties(dftbplus.energy)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        calc.execute([water(), water()])
    messages = [str(item.message) for item in caught if "ignores" in str(item.message)]
    assert messages == [
        "Driver 'fake-lib' ignores the execution setting 'ram'",
        "Driver 'fake-lib' ignores the execution setting 'timeout'",
    ]


def test_configure_only_checks_the_driver_name(
    tmp_path, fake_drivers, stub_spec, dftbp_configured, monkeypatch
):
    monkeypatch.setattr(amac, "_STATE", amac._FacadeState())
    with pytest.raises(ValueError, match="Available: amac, auto, fake-lib"):
        amac.configure(software="DFTB+", driver="nope")
    amac.configure(software="DFTB+", driver="fake-lib")
    parameters = {key: value for key, value in stub_spec.items() if key != "software"}
    with pytest.raises(DriverUnavailableError, match="pip install amac-fake-lib"):
        amac.calculator(parameters, platform="DFTB+", workdir=tmp_path)


def test_import_amac_without_library():
    """``import amac`` pulls in no driver library, even for a known software."""
    code = (
        "import sys, amac; from amac.engine.registry import get_software; "
        "get_software('DFTB+'); "
        "print(sorted({'hsd', 'dftbplus'} & set(sys.modules)))"
    )
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "[]"
