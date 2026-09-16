"""Tests of amac.engine.handlers with the dummy software."""

import pytest

from amac.assets import _dummy
from amac.assets._dummy.dummy import DummySoftware
from amac.engine import registry
from amac.engine.context import RunContext
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


def make_spec(module: str = "SINGLE_POINT") -> CalculationSpec:
    return CalculationSpec.from_kwargs(
        method="DFT",
        method_args={"variant": "PBE"},
        module=module,
        parameters={"BASIS": "sto-3g"},
    )


def make_ctx(directory, **exec_kwargs) -> RunContext:
    exec_spec = ExecutionSpec(workdir=directory, **exec_kwargs)
    return RunContext(None, make_spec(), exec_spec, directory)


def broken(ctx):
    return 1 / 0


def label(ctx):
    return ctx.exec_spec.label


@pytest.fixture
def dummy_handlers(monkeypatch):
    """Let a test register handlers on DummySoftware without leaking them."""
    monkeypatch.setattr(DummySoftware, "HANDLERS", dict(DummySoftware.HANDLERS))


@pytest.fixture
def other_software(monkeypatch):
    """Register a second software in a copy of the global registry."""
    monkeypatch.setattr(registry, "_REGISTRY", dict(registry._REGISTRY))

    class OtherSoftware(FileIOSoftware):
        NAME = "OTHER_TEST"

        def command(self, ctx):
            return []

    return registry.register_software(OtherSoftware)


def test_dummy_handlers_on_real_cycle(tmp_path):
    ctx = make_ctx(tmp_path)
    software = DummySoftware()
    software.prepare(ctx)
    software.run(ctx)
    software.collect(ctx)
    handlers = resolve_handlers(DummySoftware, ctx.spec, [_dummy.energy, _dummy.forces])
    properties, errors = run_handlers(ctx, handlers)
    assert errors == []
    assert properties["energy"] == pytest.approx(-1.0, abs=1e-12)
    assert properties["forces"] == []
    assert _dummy.energy(ctx) == pytest.approx(-1.0, abs=1e-12)


def test_decorator_registers_and_attaches_metadata():
    assert DummySoftware.HANDLERS == {
        "energy": _dummy.energy,
        "forces": _dummy.forces,
        "native_energy": _dummy.native_energy,
    }
    meta = getattr(_dummy.energy, HANDLER_ATTRIBUTE)
    assert meta == HandlerSpec("energy", _dummy.energy, DummySoftware, ("output.json",))


def test_custom_handlers(tmp_path):
    def file_count(ctx):
        return len(ctx.files)

    items = [file_count, ("label", lambda ctx: ctx.exec_spec.label)]
    handlers = resolve_handlers(DummySoftware, make_spec(), items)
    ctx = make_ctx(tmp_path, label="calc")
    assert run_handlers(ctx, handlers) == ({"file_count": 0, "label": "calc"}, [])


def test_custom_lambda_needs_a_name():
    with pytest.raises(ValueError, match="no usable name"):
        resolve_handlers(DummySoftware, make_spec(), [lambda ctx: 0])


def test_handler_of_other_software_refused(other_software):
    @handler(software="other_test")
    def other_energy(ctx):
        return 0.0

    assert other_software.HANDLERS == {"other_energy": other_energy}
    with pytest.raises(ValueError, match="belongs to OTHER_TEST, not to DUMMY"):
        resolve_handlers(DummySoftware, make_spec(), [other_energy])


def test_modules_compatibility(dummy_handlers):
    @handler(software="DUMMY", modules=("GEOMETRY_OPTIMISATION",))
    def final_geometry(ctx):
        return None

    with pytest.raises(ValueError, match="module 'SINGLE_POINT'"):
        resolve_handlers(DummySoftware, make_spec(), [final_geometry])
    spec = make_spec("geometry_optimisation")
    assert resolve_handlers(DummySoftware, spec, [final_geometry])[0].name == (
        "final_geometry"
    )


def test_drivers_compatibility(dummy_handlers):
    @handler(software="DUMMY", drivers=("opi",))
    def native(ctx):
        return ctx.objects["output"]

    with pytest.raises(ValueError, match="driver 'amac'"):
        resolve_handlers(DummySoftware, make_spec(), [native])
    resolved = resolve_handlers(DummySoftware, make_spec(), [native], driver="OPI")
    assert resolved[0].name == "native"


def test_duplicate_result_name():
    items = [_dummy.energy, ("energy", lambda ctx: 0.0)]
    with pytest.raises(ValueError, match="Duplicate result name 'energy'"):
        resolve_handlers(DummySoftware, make_spec(), items)


def test_failing_handler_is_collected(tmp_path):
    handlers = resolve_handlers(DummySoftware, make_spec(), [broken, label])
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
    handlers = resolve_handlers(DummySoftware, make_spec(), [broken, label])
    with pytest.raises(HandlerError, match="broken") as excinfo:
        run_handlers(make_ctx(tmp_path, **exec_kwargs), handlers, on_error=on_error)
    assert isinstance(excinfo.value.__cause__, ZeroDivisionError)


def test_missing_required_files(tmp_path, dummy_handlers):
    calls = []

    @handler(software="DUMMY", requires_files=("output.json", "*.log"))
    def needs_files(ctx):
        calls.append(ctx)
        return "called"

    ctx = make_ctx(tmp_path)
    ctx.files["output.json"] = tmp_path / "output.json"
    handlers = resolve_handlers(DummySoftware, ctx.spec, [needs_files])
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


def test_duplicate_handler_in_software(dummy_handlers):
    with pytest.raises(ValueError, match="already registered for DUMMY"):

        @handler(software="DUMMY")
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
