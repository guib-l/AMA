"""Tests of the specification, context and result types."""

import dataclasses
from pathlib import Path

import pytest

from amac.engine.context import Result, RunContext
from amac.parameter.parameters import DEFAULT_MODULE, CalculationSpec, ExecutionSpec


def test_calculation_spec_normalisation():
    method_args = {"variant": "PBE", "Nested": {"key": 1}}
    spec = CalculationSpec(
        method="dft",
        method_args=method_args,
        module="opt",
        parameters={"basis": "sto-3g", "Scf": {"MaxIter": 5}},
        raw="! Extra",
    )
    assert (spec.method, spec.module) == ("DFT", "OPT")
    assert spec.parameters == {"BASIS": "sto-3g", "SCF": {"MaxIter": 5}}
    assert spec.method_args == {"variant": "PBE", "Nested": {"key": 1}}
    method_args["Nested"]["key"] = 2
    assert spec.method_args["Nested"]["key"] == 1
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.method = "HF"


def test_calculation_spec_defaults():
    spec = CalculationSpec.from_kwargs("HF")
    assert spec.module == DEFAULT_MODULE
    assert (spec.method_args, spec.module_args, spec.parameters) == ({}, {}, {})
    assert spec.raw is None


@pytest.mark.parametrize(
    ("kwargs", "error", "match"),
    [
        ({"method": 1}, TypeError, "method must be a str"),
        ({"method": "HF", "module": None}, TypeError, "module must be a str"),
        ({"method": "HF", "parameters": []}, TypeError, "parameters must be a dict"),
        ({"method": "HF", "parameters": {1: "x"}}, TypeError, "keys must be str"),
        (
            {"method": "HF", "parameters": {"scf": 1, "SCF": 2}},
            ValueError,
            "Duplicate",
        ),
    ],
)
def test_calculation_spec_invalid(kwargs, error, match):
    with pytest.raises(error, match=match):
        CalculationSpec(**kwargs)


@pytest.mark.parametrize("raw", [None, "! Extra", ["a", "b"], {"Block": {"Key": 1}}])
def test_calculation_spec_round_trip(raw):
    spec = CalculationSpec.from_kwargs(
        "DFT", {"variant": "PBE"}, "OPT", {"MaxSteps": 3}, {"BASIS": "x"}, raw
    )
    assert CalculationSpec.from_dict(spec.to_dict()) == spec


def test_calculation_spec_unknown_key():
    with pytest.raises(ValueError, match="Unknown CalculationSpec keys"):
        CalculationSpec.from_dict({"method": "HF", "cpu": 1})


def test_execution_spec_defaults_and_normalisation():
    spec = ExecutionSpec()
    assert (spec.cpu, spec.ram, spec.workdir, spec.outdir) == (1, None, Path("."), None)
    assert (spec.driver, spec.handler_errors) == ("amac", "collect")
    assert (spec.raise_on_error, spec.keep_files, spec.overwrite) == (True, True, False)
    env = {"A": "1"}
    spec = ExecutionSpec(workdir="runs", outdir="out", env=env)
    env["A"] = "2"
    assert (spec.workdir, spec.outdir) == (Path("runs"), Path("out"))
    assert spec.env == {"A": "1"}


def test_execution_spec_round_trip():
    spec = ExecutionSpec(
        cpu=4,
        ram=2000,
        workdir="runs",
        outdir="out",
        timeout=12.5,
        label="calc",
        executable="/opt/prog",
        env={"OMP_NUM_THREADS": "2"},
        raise_on_error=False,
        keep_files=False,
        overwrite=True,
        handler_errors="raise",
        driver="auto",
    )
    data = spec.to_dict()
    assert (data["workdir"], data["outdir"]) == ("runs", "out")
    assert ExecutionSpec.from_dict(data) == spec
    with pytest.raises(ValueError, match="Unknown ExecutionSpec keys"):
        ExecutionSpec.from_dict(data | {"memory": 1})
    with pytest.raises(TypeError, match="driver must be a str"):
        ExecutionSpec(driver=None)


def test_run_context_and_result_round_trip(tmp_path):
    spec = CalculationSpec.from_kwargs("HF")
    ctx = RunContext(None, spec, ExecutionSpec(), str(tmp_path))
    assert ctx.directory == tmp_path
    assert (ctx.driver, ctx.return_code) == ("amac", None)
    assert ctx.files == ctx.timings == {}
    result = Result(False, {"energy": -1.0}, {"software": "DUMMY"}, ["boom"], ctx)
    data = result.to_dict()
    assert "context" not in data
    restored = Result.from_dict(data)
    assert restored.to_dict() == data
    assert restored.context is None
    with pytest.raises(ValueError, match="Unknown Result keys"):
        Result.from_dict(data | {"context": None})
