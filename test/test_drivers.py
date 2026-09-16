"""Tests of the optional library drivers with the dummy software and a fake library."""

import importlib
import json
import subprocess
import sys
import warnings
from pathlib import Path

import pytest
from ase import Atoms

import amac
from amac import AMAC
from amac.assets import _dummy
from amac.assets._dummy.dummy import DummyLibraryDriver, DummySoftware
from amac.engine import registry
from amac.engine.drivers import (
    Driver,
    DriverSelection,
    select_driver,
    validate_driver_name,
)
from amac.exceptions import DriverUnavailableError, RunError, ValidationError

ROOT = Path(__file__).resolve().parents[1]
FAKE_MODULES = ("amac_dummy_lib", "amac_probe_pkg")
FALLBACK = (
    "dummy-lib: missing Python module amac_dummy_lib (pip install amac-dummy-lib)"
)
PARAMETERS = {
    "method": "DFT",
    "method_args": {"variant": "PBE"},
    "parameters": {"BASIS": "sto-3g"},
}

LIBRARY = '''\
"""Fake dedicated library of the dummy software, created by the tests."""

import json
from pathlib import Path


class Output:
    def __init__(self, energy, forces, method):
        self.energy = energy
        self.forces = forces
        self.method = method


def write_input(spec, directory):
    path = Path(directory) / "input.json"
    path.write_text(json.dumps(spec, sort_keys=True), encoding="utf-8")
    return path


def compute(directory, cpu=1):
    directory = Path(directory)
    spec = json.loads((directory / "input.json").read_text(encoding="utf-8"))
    result = {"energy": -2.0, "forces": [], "method": spec["method"], "cpu": cpu}
    (directory / "output.json").write_text(json.dumps(result), encoding="utf-8")


def read_output(directory):
    path = Path(directory) / "output.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return Output(data["energy"], data["forces"], data["method"])
'''


def water() -> Atoms:
    positions = [[0.0, 0.0, 0.0], [0.76, 0.59, 0.0], [-0.76, 0.59, 0.0]]
    return Atoms("OH2", positions=positions)


def make_calc(tmp_path, **kwargs) -> AMAC:
    arguments = {"software": "dummy", "workdir": tmp_path / "work", **PARAMETERS}
    return AMAC(**arguments | {"validate": "off"} | kwargs)


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    """No executable variable during the test, no fake module left after it."""
    monkeypatch.delenv("DUMMY_EXECUTABLE", raising=False)
    yield
    for name in list(sys.modules):
        if name.split(".")[0] in FAKE_MODULES:
            del sys.modules[name]
    importlib.invalidate_caches()


@pytest.fixture
def dummy_lib(tmp_path, monkeypatch):
    """Make amac_dummy_lib 1.2.3 importable from a temporary sys.path entry."""
    site = tmp_path / "site"
    (site / "amac_dummy_lib").mkdir(parents=True)
    (site / "amac_dummy_lib" / "__init__.py").write_text(LIBRARY, encoding="utf-8")
    metadata = site / "amac_dummy_lib-1.2.3.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: amac-dummy-lib\nVersion: 1.2.3\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(site))
    return site


@pytest.fixture
def isolated_registry(monkeypatch):
    """Register test software in a copy of the global registry."""
    monkeypatch.setattr(registry, "_REGISTRY", dict(registry._REGISTRY))
    return registry.register_software


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


def test_is_available_does_not_import(dummy_lib):
    probe = dummy_lib / "amac_probe_pkg"
    probe.mkdir()
    (probe / "__init__.py").write_text('raise ImportError("imported")\n', "utf-8")
    (probe / "sub.py").write_text("", encoding="utf-8")
    importlib.invalidate_caches()

    class ProbeDriver(DummyLibraryDriver):
        NAME = "probe"
        REQUIRES = ("amac_probe_pkg.sub",)

    class AbsentDriver(DummyLibraryDriver):
        NAME = "absent"
        REQUIRES = ("amac_probe_pkg.absent", "amac_absent_lib")

    assert DummyLibraryDriver().is_available()
    assert ProbeDriver().is_available()
    assert AbsentDriver().missing_modules() == [
        "amac_probe_pkg.absent",
        "amac_absent_lib",
    ]
    assert DummyLibraryDriver().version() == "1.2.3"
    assert not set(FAKE_MODULES) & sys.modules.keys()


def test_driver_without_library():
    driver = DummyLibraryDriver()
    assert not driver.is_available()
    assert driver.version() is None


def test_select_driver_names():
    assert select_driver(DummySoftware, "AMAC") == DriverSelection()
    unknown = "'opi' for DUMMY. Available: amac, auto, dummy-lib"
    with pytest.raises(ValueError, match=unknown):
        select_driver(DummySoftware, "opi")
    with pytest.raises(TypeError, match="driver must be a str"):
        select_driver(DummySoftware, None)
    validate_driver_name(DummySoftware, "Dummy-Lib")
    with pytest.raises(ValueError, match="Available"):
        validate_driver_name(DummySoftware, "opi")


def test_explicit_driver_available(tmp_path, dummy_lib):
    calc = make_calc(tmp_path, driver="Dummy-Lib", cpu=2)
    assert (calc.driver.name, calc.driver.fallback) == ("dummy-lib", None)
    assert isinstance(calc.driver.driver, DummyLibraryDriver)
    calc.handler_properties(_dummy.energy, _dummy.native_energy)
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        result = calc.execute(water())

    assert (result.success, result.errors) == (True, [])
    assert result.properties["energy"] == pytest.approx(-2.0, abs=1e-12)
    assert result.properties["native_energy"] == pytest.approx(-2.0, abs=1e-12)
    ctx = result.context
    assert (ctx.driver, ctx.stdout) == ("dummy-lib", None)
    assert "input_tree" not in ctx.metadata
    assert (set(ctx.input_files), set(ctx.files)) == ({"input.json"}, {"output.json"})
    output = json.loads(ctx.files["output.json"].read_text(encoding="utf-8"))
    assert (output["cpu"], output["method"]) == (2, "DFT")
    assert calc.to_dict()["exec_spec"]["driver"] == "Dummy-Lib"

    [loaded] = amac.load(calc.store(tmp_path / "driver"))
    provenance = loaded.provenance
    assert provenance["driver"] == "dummy-lib"
    assert provenance["driver_version"] == "1.2.3"
    assert provenance["driver_fallback"] is None
    assert loaded.properties["native_energy"] == pytest.approx(-2.0, abs=1e-12)


def test_explicit_driver_unavailable(tmp_path):
    with pytest.raises(DriverUnavailableError, match="pip install amac-dummy-lib"):
        make_calc(tmp_path, driver="dummy-lib")
    with pytest.raises(ValueError, match="Available: amac, auto, dummy-lib"):
        make_calc(tmp_path, driver="opi")


def test_default_driver_is_amac(tmp_path, dummy_lib):
    calc = make_calc(tmp_path)
    assert calc.driver == DriverSelection()
    calc.handler_properties(_dummy.energy)
    result = calc.execute(water())
    assert result.properties["energy"] == pytest.approx(-1.0, abs=1e-12)
    assert "input_tree" not in result.context.metadata


def test_auto_without_library(tmp_path):
    calc = make_calc(tmp_path, driver="auto")
    assert (calc.driver.name, calc.driver.fallback) == ("amac", FALLBACK)
    calc.handler_properties(_dummy.energy)
    result = calc.execute(water())
    assert result.properties["energy"] == pytest.approx(-1.0, abs=1e-12)
    provenance = result.provenance
    assert (provenance["driver"], provenance["driver_version"]) == ("amac", None)
    assert provenance["driver_fallback"] == FALLBACK


def test_auto_with_library(tmp_path, dummy_lib):
    calc = make_calc(tmp_path, driver="auto")
    assert (calc.driver.name, calc.driver.fallback) == ("dummy-lib", None)
    calc.handler_properties(_dummy.energy)
    result = calc.execute(water())
    assert result.properties["energy"] == pytest.approx(-2.0, abs=1e-12)
    provenance = result.provenance
    assert provenance["driver"] == "dummy-lib"
    assert provenance["driver_version"] == "1.2.3"
    assert calc.to_dict()["exec_spec"]["driver"] == "auto"


def test_collect_only_driver(tmp_path, dummy_lib, isolated_registry):
    class CollectOnlyDriver(DummyLibraryDriver):
        NAME = "dummy-lib-collect"
        PHASES = frozenset({"collect"})

    class CollectSoftware(DummySoftware):
        NAME = "COLLECT_DRIVER_TEST"
        DRIVERS = (CollectOnlyDriver,)

    isolated_registry(CollectSoftware)
    calc = make_calc(
        tmp_path, software="collect_driver_test", driver="dummy-lib-collect", ram=1000
    )
    calc.handler_properties(_dummy.energy)
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        result = calc.execute(water())

    ctx = result.context
    assert result.properties["energy"] == pytest.approx(-1.0, abs=1e-12)
    assert ctx.stdout == "dummy: done\n"
    assert set(ctx.input_files) == {"input.json"}
    assert ctx.objects["dummy_lib"].energy == pytest.approx(-1.0, abs=1e-12)
    assert set(ctx.files) == {"output.json"}


def test_check_environment_failure(tmp_path, dummy_lib, isolated_registry):
    class PickyDriver(DummyLibraryDriver):
        NAME = "picky"

        def check_environment(self, software):
            return f"{software.name} is too old"

    class PickySoftware(DummySoftware):
        NAME = "PICKY_TEST"
        DRIVERS = (PickyDriver, DummyLibraryDriver)

    class PickyOnlySoftware(DummySoftware):
        NAME = "PICKY_ONLY_TEST"
        DRIVERS = (PickyDriver,)

    isolated_registry(PickySoftware)
    isolated_registry(PickyOnlySoftware)
    with pytest.raises(DriverUnavailableError, match="PICKY_TEST is too old"):
        make_calc(tmp_path, software="picky_test", driver="picky")
    auto = make_calc(tmp_path, software="picky_test", driver="auto")
    assert (auto.driver.name, auto.driver.fallback) == ("dummy-lib", None)
    fallback = make_calc(tmp_path, software="picky_only_test", driver="auto").driver
    assert (fallback.name, fallback.fallback) == (
        "amac",
        "picky: PICKY_ONLY_TEST is too old",
    )


def test_handler_drivers_are_checked_against_the_selected_driver(tmp_path):
    with pytest.raises(ValueError, match="driver 'amac'; compatible: dummy-lib"):
        make_calc(tmp_path).handler_properties(_dummy.native_energy)
    auto = make_calc(tmp_path, driver="auto")
    with pytest.raises(ValueError, match="fell back to it: dummy-lib: missing"):
        auto.handler_properties(_dummy.native_energy)


def test_raw_needs_driver_support(tmp_path, dummy_lib):
    with pytest.raises(ValidationError, match="does not support raw keywords"):
        make_calc(tmp_path, driver="dummy-lib", raw={"Extra": 1})
    auto = make_calc(tmp_path, driver="auto", raw={"Extra": 1})
    assert (auto.driver.name, auto.driver.fallback) == (
        "amac",
        "dummy-lib: does not support raw keywords",
    )


def test_driver_phase_failure_is_a_failed_run(tmp_path, dummy_lib, monkeypatch):
    import amac_dummy_lib

    calls = []

    def crash(directory, cpu=1):
        calls.append(directory)
        raise RuntimeError("library crashed")

    monkeypatch.setattr(amac_dummy_lib, "compute", crash)
    calc = make_calc(tmp_path, driver="dummy-lib")
    calc.handler_properties(_dummy.energy)
    with pytest.raises(RunError, match="library crashed") as excinfo:
        calc.execute(water())
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert excinfo.value.ctx.driver == "dummy-lib"
    assert (excinfo.value.ctx.stdout, excinfo.value.ctx.files) == (None, {})

    calc = make_calc(tmp_path, driver="dummy-lib", raise_on_error=False, label="kept")
    calc.handler_properties(_dummy.energy)
    result = calc.execute(water())
    assert (result.success, result.properties) == (False, {})
    assert isinstance(result.errors[0], RunError)
    assert (result.context.stdout, result.context.return_code) == (None, None)
    assert len(calls) == 2


def test_ignored_settings_warn_once_per_execute(tmp_path, dummy_lib):
    calc = make_calc(tmp_path, driver="dummy-lib", cpu=4, ram=1000, timeout=30.0)
    calc.handler_properties(_dummy.energy)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        calc.execute([water(), water()])
    messages = [str(item.message) for item in caught if "ignores" in str(item.message)]
    assert messages == [
        "Driver 'dummy-lib' ignores the execution setting 'ram'",
        "Driver 'dummy-lib' ignores the execution setting 'timeout'",
    ]


def test_configure_only_checks_the_driver_name(tmp_path, monkeypatch):
    monkeypatch.setattr(amac, "_STATE", amac._FacadeState())
    with pytest.raises(ValueError, match="Available: amac, auto, dummy-lib"):
        amac.configure(software="dummy", driver="nope")
    amac.configure(software="dummy", driver="dummy-lib")
    with pytest.raises(DriverUnavailableError, match="pip install amac-dummy-lib"):
        amac.calculator(PARAMETERS, platform="dummy", workdir=tmp_path, validate="off")


def test_import_amac_without_library():
    code = (
        "import sys, amac; from amac.engine.registry import get_software; "
        "get_software('dummy'); print(sorted({'amac_dummy_lib'} & set(sys.modules)))"
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
