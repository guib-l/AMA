"""Tests of the normalized output pattern, on the DFTB+ asset driven by the stub.

The pattern is generic: a software (or a collecting driver) leaves its normalized
output in ``ctx.objects[OUTPUT_KEY]``, and the handlers read it through
``cached_output`` so that the files are parsed once per run.
"""

import numpy as np
import pytest
from ase.units import Hartree
from conftest import STUB_ENERGY, stub_charges

import amac
from amac.assets import dftbplus
from amac.assets.dftbplus import handlers as dftbplus_handlers
from amac.assets.dftbplus.parser import DETAILED_OUT, DftbPlusOutput
from amac.engine.context import OUTPUT_KEY, RunContext, cached_output
from amac.exceptions import HandlerError


def test_cached_output_parses_once(tmp_path, stub_calc, water):
    calc = stub_calc()
    ctx = RunContext(water, calc.spec, calc.exec_spec, tmp_path)
    calls = []

    def parse(directory):
        calls.append(directory)
        return DftbPlusOutput(energy=-3.0)

    first = cached_output(ctx, parse)
    assert first == DftbPlusOutput(energy=-3.0)
    assert ctx.objects[OUTPUT_KEY] is first
    assert cached_output(ctx, parse) is first
    assert calls == [tmp_path]


def test_the_handlers_of_a_run_share_one_parsing(stub_calc, water, monkeypatch):
    """Two handlers, one reading of the output files."""
    calls = []
    original = dftbplus_handlers.parse_directory

    def counted(directory):
        calls.append(directory)
        return original(directory)

    monkeypatch.setattr(dftbplus_handlers, "parse_directory", counted)
    calc = stub_calc()
    calc.handler_properties(dftbplus.energy, dftbplus.charges)
    result = calc.execute(water)

    assert calls == [result.context.directory]
    output = result.context.objects[OUTPUT_KEY]
    assert isinstance(output, DftbPlusOutput)
    assert output.energy == pytest.approx(STUB_ENERGY)
    assert result.properties["energy"] == pytest.approx(STUB_ENERGY * Hartree)
    assert result.properties["charges"] == pytest.approx(stub_charges(len(water)))


def test_requires_files_applies_to_the_output(stub_calc, water):
    """A handler whose files are gone is skipped, and nothing is parsed."""
    calc = stub_calc()
    calc.handler_properties(dftbplus.energy)
    directory = calc.execute(water).context.directory
    (directory / DETAILED_OUT).unlink()

    again = calc.reprocess(directory)
    assert again.success
    assert again.properties == {}
    assert OUTPUT_KEY not in again.context.objects
    [error] = again.errors
    assert isinstance(error, HandlerError)
    assert f"missing files: {DETAILED_OUT}" in str(error)


def test_reprocess_rebuilds_the_output_from_the_files(stub_calc, water):
    """A calculator that never ran can read the directory of another one."""
    written = stub_calc(label="written")
    written.handler_properties(dftbplus.energy)
    directory = written.execute(water).context.directory

    calc = stub_calc(label="other")
    again = calc.reprocess(directory, handlers=[dftbplus.energy, dftbplus.forces])
    assert again.properties["energy"] == pytest.approx(STUB_ENERGY * Hartree)
    assert np.asarray(again.properties["forces"]).shape == (len(water), 3)
    assert again.context.objects[OUTPUT_KEY].energy == pytest.approx(STUB_ENERGY)
    assert again.provenance["reprocessed"]


def test_module_reprocess_rebuilds_the_output_from_the_files(stub_calc, water):
    calc = stub_calc()
    calc.handler_properties(dftbplus.forces)
    result = calc.execute(water)
    assert result.context.objects[OUTPUT_KEY].energy == pytest.approx(STUB_ENERGY)

    again = amac.reprocess(result, [dftbplus.energy])
    assert again.context.objects[OUTPUT_KEY].energy == pytest.approx(STUB_ENERGY)
    assert again.properties["energy"] == pytest.approx(STUB_ENERGY * Hartree)
