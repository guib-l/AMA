"""Tests of amac.engine.handlers, on the DFTB+ asset driven by the stub program."""

import numpy as np
import pytest
from ase.units import Bohr, Hartree
from conftest import STUB_ENERGY, stub_forces

from amac.assets import dftbplus
from amac.assets.dftbplus.dftbplus import DftbPlus
from amac.assets.dftbplus.parser import DETAILED_OUT
from amac.engine import registry
from amac.engine.context import RunContext
from amac.engine.drivers import Driver
from amac.engine.handlers import (
    HANDLER_ATTRIBUTE,
    HandlerSpec,
    handler,
    resolve_handlers,
    run_handlers,
)
from amac.engine.software import FileIOSoftware
from amac.exceptions import HandlerError, SoftwareNotFoundError
from amac.parameter.parameters import CalculationSpec, ExecutionSpec

# Handlers exposed by the DFTB+ package; every one of them is registered.
DFTBP_HANDLERS = {
    "energy",
    "forces",
    "charges",
    "dipole",
    "orbital_energies",
    "final_geometry",
}


def make_spec(module: str = "SINGLE_POINT") -> CalculationSpec:
    return CalculationSpec.from_kwargs(
        method="TIGHT_BINDING",
        method_args={"variant": "DFTB2", "MaxAngularMomentum": {"O": "p", "H": "s"}},
        module=module,
        parameters={"SLATER_KOSTER_FILES": {"variant": "Type2FileNames"}},
    )


def make_ctx(directory, atoms=None, **exec_kwargs) -> RunContext:
    exec_spec = ExecutionSpec(workdir=directory, **exec_kwargs)
    return RunContext(atoms, make_spec(), exec_spec, directory, software=DftbPlus())


def broken(ctx):
    return 1 / 0


def label(ctx):
    return ctx.exec_spec.label


@pytest.fixture
def dftbp_handlers(monkeypatch):
    """Let a test register handlers on DftbPlus without leaking them."""
    monkeypatch.setattr(DftbPlus, "HANDLERS", dict(DftbPlus.HANDLERS))


@pytest.fixture
def other_software(monkeypatch):
    """Register a second software in a copy of the global registry."""
    monkeypatch.setattr(registry, "_REGISTRY", dict(registry._REGISTRY))

    class OtherSoftware(FileIOSoftware):
        NAME = "OTHER_TEST"

        def command(self, ctx):
            return []

    return registry.register_software(OtherSoftware)


def test_handlers_on_a_real_cycle(tmp_path, water, dftbp_stub, dftbp_configured):
    """prepare, run and collect, then the handlers read what the run produced."""
    ctx = make_ctx(tmp_path, atoms=water, executable=str(dftbp_stub()))
    software = DftbPlus()
    software.prepare(ctx)
    software.run(ctx)
    software.collect(ctx)

    handlers = resolve_handlers(DftbPlus, ctx.spec, [dftbplus.energy, dftbplus.forces])
    properties, errors = run_handlers(ctx, handlers)
    assert errors == []
    assert properties["energy"] == pytest.approx(STUB_ENERGY * Hartree)
    assert properties["forces"] == pytest.approx(
        np.asarray(stub_forces(len(water))) * (Hartree / Bohr)
    )


def test_decorator_registers_and_attaches_metadata():
    assert set(DftbPlus.HANDLERS) == DFTBP_HANDLERS
    assert DftbPlus.HANDLERS["energy"] is dftbplus.energy
    meta = getattr(dftbplus.energy, HANDLER_ATTRIBUTE)
    assert meta == HandlerSpec("energy", dftbplus.energy, DftbPlus, (DETAILED_OUT,))


def test_custom_handlers(tmp_path):
    def file_count(ctx):
        return len(ctx.files)

    items = [file_count, ("label", lambda ctx: ctx.exec_spec.label)]
    handlers = resolve_handlers(DftbPlus, make_spec(), items)
    ctx = make_ctx(tmp_path, label="calc")
    assert run_handlers(ctx, handlers) == ({"file_count": 0, "label": "calc"}, [])


def test_custom_lambda_needs_a_name():
    with pytest.raises(ValueError, match="no usable name"):
        resolve_handlers(DftbPlus, make_spec(), [lambda ctx: 0])


def test_handler_of_other_software_refused(other_software):
    @handler(software="other_test")
    def other_energy(ctx):
        return 0.0

    assert other_software.HANDLERS == {"other_energy": other_energy}
    with pytest.raises(ValueError, match="belongs to OTHER_TEST, not to DFTBP"):
        resolve_handlers(DftbPlus, make_spec(), [other_energy])


def test_modules_compatibility():
    """``final_geometry`` is declared for the optimisation modules only."""
    with pytest.raises(ValueError, match="module 'SINGLE_POINT'"):
        resolve_handlers(DftbPlus, make_spec(), [dftbplus.final_geometry])
    spec = make_spec("geometry_optimisation")
    resolved = resolve_handlers(DftbPlus, spec, [dftbplus.final_geometry])
    assert resolved[0].name == "final_geometry"


def test_drivers_compatibility(dftbp_handlers):
    @handler(software="DFTBP", drivers=("dftbplus-api",))
    def native(ctx):
        return ctx.objects["output"]

    with pytest.raises(ValueError, match="driver 'amac'"):
        resolve_handlers(DftbPlus, make_spec(), [native])
    resolved = resolve_handlers(DftbPlus, make_spec(), [native], driver="DFTBPLUS-API")
    assert resolved[0].name == "native"


def test_duplicate_result_name():
    items = [dftbplus.energy, ("energy", lambda ctx: 0.0)]
    with pytest.raises(ValueError, match="Duplicate result name 'energy'"):
        resolve_handlers(DftbPlus, make_spec(), items)


def test_failing_handler_is_collected(tmp_path):
    handlers = resolve_handlers(DftbPlus, make_spec(), [broken, label])
    properties, errors = run_handlers(make_ctx(tmp_path, label="calc"), handlers)
    assert properties == {"label": "calc"}
    [error] = errors
    assert isinstance(error, HandlerError)
    assert error.handler == "broken"
    assert "broken" in str(error)
    assert isinstance(error.__cause__, ZeroDivisionError)


@pytest.mark.parametrize(
    ("exec_kwargs", "on_error"),
    [({"handler_errors": "raise"}, None), ({}, "raise")],
    ids=["exec-spec", "argument"],
)
def test_failing_handler_is_raised(tmp_path, exec_kwargs, on_error):
    handlers = resolve_handlers(DftbPlus, make_spec(), [broken, label])
    with pytest.raises(HandlerError, match="broken") as excinfo:
        run_handlers(make_ctx(tmp_path, **exec_kwargs), handlers, on_error=on_error)
    assert isinstance(excinfo.value.__cause__, ZeroDivisionError)


def test_missing_required_files(tmp_path, dftbp_handlers):
    calls = []

    @handler(software="DFTBP", requires_files=(DETAILED_OUT, "*.log"))
    def needs_files(ctx):
        calls.append(ctx)
        return "called"

    ctx = make_ctx(tmp_path)
    ctx.files[DETAILED_OUT] = tmp_path / DETAILED_OUT
    handlers = resolve_handlers(DftbPlus, ctx.spec, [needs_files])
    properties, [error] = run_handlers(ctx, handlers)
    assert (properties, calls) == ({}, [])
    assert error.handler == "needs_files"
    assert error.missing_files == ("*.log",)
    assert "missing files: *.log" in str(error)
    ctx.files["run.log"] = tmp_path / "run.log"
    assert run_handlers(ctx, handlers) == ({"needs_files": "called"}, [])


def test_no_handler_warns(tmp_path):
    with pytest.warns(UserWarning, match="No handler"):
        assert run_handlers(make_ctx(tmp_path), []) == ({}, [])


def test_unknown_software_at_decoration():
    with pytest.raises(SoftwareNotFoundError, match="'NOPE'"):
        handler(software="NOPE")


def test_duplicate_handler_in_software(dftbp_handlers):
    with pytest.raises(ValueError, match="already registered for DFTBP"):

        @handler(software="DFTBP")
        def energy(ctx):
            return 0.0


def test_handler_errors_option(tmp_path):
    exec_spec = ExecutionSpec(handler_errors="raise")
    assert ExecutionSpec.from_dict(exec_spec.to_dict()) == exec_spec
    assert ExecutionSpec().handler_errors == "collect"
    with pytest.raises(ValueError, match="handler_errors"):
        ExecutionSpec(handler_errors="strict")
    with pytest.raises(ValueError, match="on_error"):
        run_handlers(make_ctx(tmp_path), [], on_error="strict")


@handler(requires_files=(DETAILED_OUT,))
def output_size(ctx) -> int:
    """Custom handler with requires_files, attached to no software."""
    return ctx.files[DETAILED_OUT].stat().st_size


@handler(modules=("GEOMETRY_OPTIMISATION",))
def final_step(ctx) -> None:
    """Custom handler restricted to optimisations."""


class UnavailableDriver(Driver):
    """Driver whose library is never installed, so ``auto`` always falls back."""

    NAME = "unavailable-test"
    REQUIRES = ("amac_absent_lib",)
    PHASES = frozenset({"collect"})

    def collect(self, software, ctx):
        """Collect nothing: this driver is never selected."""


def test_handler_without_software(stub_calc, water):
    """A handler declared for no software is accepted by any of them."""
    assert getattr(output_size, HANDLER_ATTRIBUTE).software is None
    assert "output_size" not in DftbPlus.HANDLERS
    calc = stub_calc()
    calc.handler_properties(output_size)
    assert calc.execute(water).properties["output_size"] > 0

    # The same handler on a run that wrote nothing: its files are missing.
    empty = stub_calc(stub={"files": ()}, label="empty")
    empty.handler_properties(output_size)
    [error] = empty.execute(water).errors
    assert error.missing_files == (DETAILED_OUT,)


def test_skip_incompatible(stub_calc, dftbp_handlers, monkeypatch):
    monkeypatch.setattr(DftbPlus, "DRIVERS", (UnavailableDriver,))

    @handler(software="DFTBP", drivers=("unavailable-test",))
    def native_energy(ctx):
        return None

    auto = stub_calc(driver="auto")
    with pytest.warns(UserWarning, match="native_energy.*fell back to it: unavailable"):
        auto.handler_properties(
            dftbplus.energy, native_energy, final_step, skip_incompatible=True
        )
    assert [meta.name for meta in auto.handlers] == ["energy"]
    with pytest.raises(ValueError, match="Duplicate result name"):
        auto.handler_properties(
            dftbplus.energy, ("energy", output_size), skip_incompatible=True
        )
    with pytest.raises(ValueError, match="module 'SINGLE_POINT'"):
        auto.handler_properties(final_step)
