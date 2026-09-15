"""Tests of the module facade: configure, calculator and run."""

import pytest
from ase import Atoms

import amac
from amac import AMAC
from amac.assets import _dummy
from amac.assets._dummy.dummy import DummySoftware
from amac.exceptions import AMACError

PARAMETERS = {
    "method": "DFT",
    "method_args": {"variant": "PBE"},
    "parameters": {"BASIS": "sto-3g"},
}


@pytest.fixture(autouse=True)
def facade_state(monkeypatch):
    """Give each test an empty configuration and no current calculator."""
    monkeypatch.setattr(amac, "_STATE", amac._FacadeState())
    monkeypatch.delenv("DUMMY_EXECUTABLE", raising=False)


def water() -> Atoms:
    positions = [[0.0, 0.0, 0.0], [0.76, 0.59, 0.0], [-0.76, 0.59, 0.0]]
    return Atoms("OH2", positions=positions)


def resolved_executable(calc: AMAC) -> str | None:
    return calc.software.resolve_executable(calc.exec_spec)


def test_manifest_example_with_dummy(tmp_path):
    amac.calculator(
        parameters=PARAMETERS,
        platform="dummy",
        handlers=[_dummy.energy, _dummy.forces],
        cpu=2,
        workdir=tmp_path,
    )
    result = amac.run(water())
    assert result.success
    assert result.properties["energy"] == pytest.approx(-1.0, abs=1e-12)
    assert result.properties["forces"] == []
    assert result.context.exec_spec.cpu == 2
    assert result.context.directory == tmp_path / "amac"


def test_execution_key_in_parameters(tmp_path):
    with pytest.raises(ValueError, match="'cpu'.*keyword argument"):
        amac.calculator(PARAMETERS | {"cpu": 2}, platform="dummy")


def test_unknown_key_in_parameters():
    with pytest.raises(ValueError, match="did you mean 'method_args'"):
        amac.calculator(PARAMETERS | {"method_arg": {}}, platform="dummy")


def test_calculation_key_in_kwargs(tmp_path):
    with pytest.raises(TypeError, match="go in parameters.*module"):
        amac.calculator(PARAMETERS, platform="dummy", module="OPT")


def test_run_without_calculator():
    with pytest.raises(AMACError, match="No current calculator"):
        amac.run(water())


def test_explicit_calc_wins_over_current(tmp_path):
    amac.calculator(
        PARAMETERS,
        platform="dummy",
        handlers=[_dummy.energy],
        workdir=tmp_path,
        label="current",
    )
    explicit = AMAC(software="dummy", workdir=tmp_path, label="explicit", **PARAMETERS)
    explicit.handler_properties(_dummy.energy)
    assert amac.run(water(), calc=explicit).context.directory.name == "explicit"
    assert amac.run(water()).context.directory.name == "current"


def test_run_handlers_for_one_call_only(tmp_path):
    calc = amac.calculator(
        PARAMETERS, platform="dummy", handlers=[_dummy.energy], workdir=tmp_path
    )
    result = amac.run(water(), handlers=[_dummy.forces], label="forces")
    assert result.properties.keys() == {"forces"}
    assert [meta.name for meta in calc.handlers] == ["energy"]
    with pytest.raises(TypeError, match="geometry"):
        amac.run("H2O", handlers=[_dummy.forces])
    assert [meta.name for meta in calc.handlers] == ["energy"]
    assert amac.run(water(), label="energy").properties.keys() == {"energy"}


def test_configure_priorities(tmp_path):
    amac.configure(cpu=2, ram=1000, timeout=60)
    amac.configure(timeout=30)
    amac.configure(software="DUMMY", cpu=3, driver="auto")
    calc = amac.calculator(PARAMETERS, platform="dummy", ram=500, workdir=tmp_path)
    assert (calc.exec_spec.cpu, calc.exec_spec.ram) == (3, 500)
    assert calc.exec_spec.timeout == pytest.approx(30.0, abs=1e-12)
    assert calc.driver.fallback.startswith("dummy-lib: missing Python module")
    explicit = amac.calculator(PARAMETERS, platform="dummy", cpu=8, driver="amac")
    assert (explicit.exec_spec.cpu, explicit.driver.fallback) == (8, None)


def test_configure_does_not_affect_direct_amac(tmp_path):
    amac.configure(cpu=4)
    amac.configure(software="dummy", executable="/configured/python", driver="auto")
    calc = AMAC(software="dummy", workdir=tmp_path, **PARAMETERS)
    assert (calc.exec_spec.cpu, calc.exec_spec.executable) == (1, None)
    assert calc.driver.fallback is None


def test_facade_executable_resolution(tmp_path, monkeypatch):
    monkeypatch.setenv("DUMMY_EXECUTABLE", "/env/python")
    assert resolved_executable(amac.calculator(PARAMETERS, "dummy")) == "/env/python"
    amac.configure(software="dummy", executable="/configured/python")
    configured = amac.calculator(PARAMETERS, "dummy")
    assert resolved_executable(configured) == "/configured/python"
    explicit = amac.calculator(PARAMETERS, "dummy", executable="/explicit/python")
    assert resolved_executable(explicit) == "/explicit/python"


def test_direct_amac_executable_resolution(tmp_path, monkeypatch):
    calc = AMAC(software="dummy", **PARAMETERS)
    assert resolved_executable(calc) is None
    monkeypatch.setenv("DUMMY_EXECUTABLE", "/env/python")
    assert resolved_executable(calc) == "/env/python"
    explicit = AMAC(software="dummy", executable="/explicit/python", **PARAMETERS)
    assert resolved_executable(explicit) == "/explicit/python"


def test_executable_env_default_and_override():
    class RenamedDummy(DummySoftware):
        NAME = "RENAMED"

    class CustomEnvDummy(DummySoftware):
        EXECUTABLE_ENV = "MY_DUMMY_BIN"

    class InheritingDummy(CustomEnvDummy):
        pass

    assert DummySoftware.EXECUTABLE_ENV == "DUMMY_EXECUTABLE"
    assert RenamedDummy.EXECUTABLE_ENV == "RENAMED_EXECUTABLE"
    assert CustomEnvDummy.EXECUTABLE_ENV == "MY_DUMMY_BIN"
    assert InheritingDummy.EXECUTABLE_ENV == "MY_DUMMY_BIN"


@pytest.mark.parametrize(
    ("kwargs", "error", "match"),
    [
        ({"executable": "/bin/x"}, ValueError, "give software="),
        ({"driver": "auto"}, ValueError, "give software="),
        ({"timout": 5}, TypeError, "did you mean 'timeout'"),
        ({"software": "dummy", "driver": "opi"}, ValueError, "Unknown driver"),
    ],
)
def test_configure_errors(kwargs, error, match):
    with pytest.raises(error, match=match):
        amac.configure(**kwargs)


def test_reset_configuration(tmp_path):
    amac.configure(cpu=4)
    amac.configure(software="dummy", executable="/configured/python")
    current = amac.calculator(PARAMETERS, "dummy", workdir=tmp_path)
    amac.reset_configuration()
    calc = amac.calculator(PARAMETERS, "dummy", workdir=tmp_path)
    assert (calc.exec_spec.cpu, calc.exec_spec.executable) == (1, None)
    assert current.exec_spec.cpu == 4


def test_public_api():
    assert set(amac.__all__) == {
        "AMAC",
        "AMACError",
        "ConfigurationError",
        "DriverUnavailableError",
        "ExecutableNotFoundError",
        "HandlerError",
        "RunError",
        "SoftwareNotFoundError",
        "ValidationError",
        "__version__",
        "available",
        "calculator",
        "configure",
        "load",
        "reprocess",
        "reset_configuration",
        "run",
        "which",
    }
    assert not any(name.startswith("_GLOBAL_") for name in vars(amac))
