"""Tests of the module facade: configure, calculator and run."""

import json
import warnings

import pytest
from ase import Atoms
from ase.units import Hartree
from conftest import STUB_ENERGY, stub_charges

import amac
from amac import AMAC, exceptions
from amac.assets import dftbplus
from amac.config import clear_config_cache
from amac.engine.software import ExecutableLocation
from amac.exceptions import AMACError

PLATFORM = "DFTB+"
PARAMETERS = {
    "method": "TIGHT_BINDING",
    "method_args": {"variant": "DFTB2", "MaxAngularMomentum": {"O": "p", "H": "s"}},
    "parameters": {
        "SLATER_KOSTER_FILES": {"variant": "Type2FileNames"},
        "ANALYSIS": {"MullikenAnalysis": True, "Printforces": True},
    },
}


@pytest.fixture(autouse=True)
def facade_state(monkeypatch, dftbp_configured):
    """Give each test an empty configuration and no current calculator."""
    monkeypatch.setattr(amac, "_STATE", amac._FacadeState())


@pytest.fixture
def executable(dftbp_stub) -> str:
    """Path of a stub ``dftb+``, as an explicit ``executable=`` always is."""
    return str(dftbp_stub())


def water() -> Atoms:
    positions = [[0.0, 0.0, 0.0], [0.76, 0.59, 0.0], [-0.76, 0.59, 0.0]]
    return Atoms("OH2", positions=positions)


def resolved_executable(calc: AMAC) -> str | None:
    return calc.software.resolve_executable(calc.exec_spec)


def write_dftbp_config(directory, executable: str, default: bool = True):
    """Write a configuration file giving the executable of DFTB+.

    Its name differs from the one of the ``write_config`` fixture, so that both
    files can exist in the same test.
    """
    path = directory / "executable-config.json"
    content = {"software": {"DFTB+": {"executable": executable}}}
    path.write_text(json.dumps(content), encoding="utf-8")
    clear_config_cache()
    if default:
        amac.set_config(path)
    return path


def test_manifest_example(tmp_path, executable):
    amac.calculator(
        parameters=PARAMETERS,
        platform=PLATFORM,
        handlers=[dftbplus.energy, dftbplus.charges],
        cpu=2,
        workdir=tmp_path,
        executable=executable,
    )
    result = amac.run(water())
    assert result.success
    assert result.properties["energy"] == pytest.approx(STUB_ENERGY * Hartree)
    assert result.properties["charges"] == pytest.approx(stub_charges(3))
    assert result.context.exec_spec.cpu == 2
    assert result.context.directory == tmp_path / "amac"


def test_execution_key_in_parameters():
    with pytest.raises(ValueError, match="'cpu'.*keyword argument"):
        amac.calculator(PARAMETERS | {"cpu": 2}, platform=PLATFORM)


def test_unknown_key_in_parameters():
    with pytest.raises(ValueError, match="did you mean 'method_args'"):
        amac.calculator(PARAMETERS | {"method_arg": {}}, platform=PLATFORM)


def test_calculation_key_in_kwargs():
    with pytest.raises(TypeError, match="go in parameters.*module"):
        amac.calculator(PARAMETERS, platform=PLATFORM, module="GEOMETRY_OPTIMISATION")


def test_run_without_calculator():
    with pytest.raises(AMACError, match="No current calculator"):
        amac.run(water())


def test_explicit_calc_wins_over_current(tmp_path, executable):
    amac.calculator(
        PARAMETERS,
        platform=PLATFORM,
        handlers=[dftbplus.energy],
        workdir=tmp_path,
        label="current",
        executable=executable,
    )
    explicit = AMAC(
        software=PLATFORM,
        workdir=tmp_path,
        label="explicit",
        executable=executable,
        **PARAMETERS,
    )
    explicit.handler_properties(dftbplus.energy)
    assert amac.run(water(), calc=explicit).context.directory.name == "explicit"
    assert amac.run(water()).context.directory.name == "current"


def test_run_handlers_for_one_call_only(tmp_path, executable):
    calc = amac.calculator(
        PARAMETERS,
        platform=PLATFORM,
        handlers=[dftbplus.energy],
        workdir=tmp_path,
        executable=executable,
    )
    result = amac.run(water(), handlers=[dftbplus.forces], label="forces")
    assert result.properties.keys() == {"forces"}
    assert [meta.name for meta in calc.handlers] == ["energy"]
    with pytest.raises(TypeError, match="geometry"):
        amac.run("H2O", handlers=[dftbplus.forces])
    assert [meta.name for meta in calc.handlers] == ["energy"]
    assert amac.run(water(), label="energy").properties.keys() == {"energy"}


def test_configure_priorities(tmp_path):
    amac.configure(cpu=2, ram=1000, timeout=60)
    amac.configure(timeout=30)
    amac.configure(software="DFTBP", cpu=3, driver="auto", validate="warn")
    calc = amac.calculator(PARAMETERS, platform=PLATFORM, ram=500, workdir=tmp_path)
    assert (calc.exec_spec.cpu, calc.exec_spec.ram) == (3, 500)
    assert calc.exec_spec.timeout == pytest.approx(30.0, abs=1e-12)
    assert (calc.exec_spec.driver, calc.validate) == ("auto", "warn")
    explicit = amac.calculator(PARAMETERS, platform=PLATFORM, cpu=8, driver="amac")
    assert (explicit.exec_spec.cpu, explicit.driver.fallback) == (8, None)


def test_configure_does_not_affect_direct_amac(tmp_path):
    amac.configure(cpu=4)
    amac.configure(software=PLATFORM, executable="/configured/dftb+", driver="auto")
    calc = AMAC(software=PLATFORM, workdir=tmp_path, **PARAMETERS)
    assert (calc.exec_spec.cpu, calc.exec_spec.executable) == (1, None)
    assert calc.driver.fallback is None


def test_facade_executable_resolution(tmp_path):
    """The file of the process, then configure(), then executable=."""
    config = write_dftbp_config(tmp_path, "/file/dftb+")
    calc = amac.calculator(PARAMETERS, PLATFORM)
    assert resolved_executable(calc) == "/file/dftb+"
    amac.configure(software=PLATFORM, executable="/configured/dftb+")
    configured = amac.calculator(PARAMETERS, PLATFORM)
    assert resolved_executable(configured) == "/configured/dftb+"
    explicit = amac.calculator(PARAMETERS, PLATFORM, executable="/explicit/dftb+")
    assert resolved_executable(explicit) == "/explicit/dftb+"
    assert amac.which(PLATFORM) == ExecutableLocation("/file/dftb+", f"file:{config}")


def test_configure_config_sets_the_file_of_the_process(tmp_path):
    """``configure(config=...)`` is process-wide, unlike the other settings."""
    config = write_dftbp_config(tmp_path, "/file/dftb+", default=False)
    assert amac.which(PLATFORM) is None
    amac.configure(config=config)
    assert resolved_executable(AMAC(software=PLATFORM, **PARAMETERS)) == "/file/dftb+"
    assert resolved_executable(amac.calculator(PARAMETERS, PLATFORM)) == "/file/dftb+"


def test_calculator_config_is_per_calculator(tmp_path):
    """``calculator(config=...)`` reaches ``AMAC`` and leaves the process alone."""
    config = write_dftbp_config(tmp_path, "/file/dftb+", default=False)
    calc = amac.calculator(PARAMETERS, PLATFORM, config=config)
    assert resolved_executable(calc) == "/file/dftb+"
    assert amac.which(PLATFORM) is None


def test_direct_amac_executable_resolution(tmp_path):
    calc = AMAC(software=PLATFORM, **PARAMETERS)
    assert resolved_executable(calc) is None
    write_dftbp_config(tmp_path, "/file/dftb+")
    assert resolved_executable(AMAC(software=PLATFORM, **PARAMETERS)) == "/file/dftb+"
    explicit = AMAC(software=PLATFORM, executable="/explicit/dftb+", **PARAMETERS)
    assert resolved_executable(explicit) == "/explicit/dftb+"


@pytest.mark.parametrize(
    ("kwargs", "error", "match"),
    [
        ({"executable": "/bin/x"}, ValueError, "give software="),
        ({"driver": "auto"}, ValueError, "give software="),
        ({"timout": 5}, TypeError, "did you mean 'timeout'"),
        ({"software": PLATFORM, "driver": "opi"}, ValueError, "Unknown driver"),
    ],
)
def test_configure_errors(kwargs, error, match):
    with pytest.raises(error, match=match):
        amac.configure(**kwargs)


def test_reset_configuration(tmp_path):
    amac.configure(cpu=4)
    amac.configure(software=PLATFORM, executable="/configured/dftb+")
    current = amac.calculator(PARAMETERS, PLATFORM, workdir=tmp_path)
    amac.reset_configuration()
    calc = amac.calculator(PARAMETERS, PLATFORM, workdir=tmp_path)
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
        "calculator",
        "configure",
        "load",
        "reprocess",
        "reset_configuration",
        "run",
        "set_config",
        "which",
    }
    assert not any(name.startswith("_GLOBAL_") for name in vars(amac))


def test_configure_validate(tmp_path, no_doc_software):
    """``validate`` goes through configure(), globally then per software."""
    parameters = {"method": "DFT", "method_args": {"variant": "PBE"}}
    amac.configure(validate="warn")
    with pytest.warns(UserWarning, match="NO_DOC_TEST has no doc.json"):
        calc = amac.calculator(parameters, "NO_DOC_TEST", workdir=tmp_path)
    assert calc.validate == "warn"
    amac.configure(software="NO_DOC_TEST", validate="off")
    assert amac.calculator(parameters, "NO_DOC_TEST").validate == "off"
    with pytest.raises(amac.ValidationError, match="NO_DOC_TEST has no doc.json"):
        amac.calculator(parameters, "NO_DOC_TEST", validate="strict")
    with pytest.raises(amac.ValidationError, match="NO_DOC_TEST has no doc.json"):
        AMAC(software="NO_DOC_TEST", **parameters)
    with pytest.raises(ValueError, match="Unknown validation mode 'lenient'"):
        amac.configure(validate="lenient")


def test_skip_incompatible_in_facade(tmp_path, executable):
    """calculator() and run() take skip_incompatible, warning once each."""
    handlers = [dftbplus.energy, dftbplus.final_geometry]
    with pytest.warns(UserWarning, match="final_geometry"):
        calc = amac.calculator(
            PARAMETERS,
            PLATFORM,
            handlers=handlers,
            skip_incompatible=True,
            workdir=tmp_path,
            executable=executable,
        )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = amac.run(
            water(),
            handlers=[dftbplus.final_geometry, dftbplus.forces],
            skip_incompatible=True,
        )
    assert any("final_geometry" in str(item.message) for item in caught)
    assert result.properties.keys() == {"forces"}
    assert [meta.name for meta in calc.handlers] == ["energy"]


def test_exceptions_are_exported():
    names = (
        "AMACError",
        "ValidationError",
        "SoftwareNotFoundError",
        "RunError",
        "HandlerError",
        "DriverUnavailableError",
    )
    for name in names:
        assert getattr(amac, name) is getattr(exceptions, name)
        assert name in amac.__all__
