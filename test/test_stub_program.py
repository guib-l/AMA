"""Tests of the stub ``dftb+`` the other tests run (see ``conftest.py``).

The stub stands in for the real program in the generic chain, so what it writes
must stay readable by the DFTB+ parser and consistent with the values the fixtures
publish.
"""

import subprocess
import sys

import numpy as np
import pytest
from ase.units import Bohr, Hartree
from conftest import (
    STUB_DISPLACEMENT,
    STUB_ENERGY,
    STUB_FERMI_LEVEL,
    stub_charges,
    stub_forces,
)

from amac.assets import dftbplus
from amac.assets.dftbplus.parser import parse_directory

INPUT_FILE = "dftb_in.hsd"


def test_stub_refuses_a_directory_without_input(dftbp_stub, tmp_path):
    """Run outside a prepared directory: the stub fails instead of inventing output."""
    completed = subprocess.run(
        [str(dftbp_stub())], cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert completed.returncode == 2
    assert "no dftb_in.hsd" in completed.stderr


@pytest.mark.filterwarnings("ignore:No handler declared")
def test_stub_output_is_read_back_by_the_dftbplus_parser(stub_calc, water):
    """The files of a stub run parse into the values the fixtures announce."""
    result = stub_calc().execute(water)
    output = parse_directory(result.context.directory)

    assert output.energy == pytest.approx(STUB_ENERGY)
    assert output.fermi_level == pytest.approx(STUB_FERMI_LEVEL)
    assert output.converged is True
    assert output.forces == pytest.approx(np.asarray(stub_forces(len(water))))
    assert output.charges == pytest.approx(np.asarray(stub_charges(len(water))))
    assert sorted(output.files) == ["detailed.out", "results.tag"]


def test_stub_run_goes_through_the_whole_chain(stub_calc, water, dftbp_configured):
    """prepare writes the input, run executes the stub, collect lists what it wrote."""
    calc = stub_calc()
    calc.handler_properties(dftbplus.energy, dftbplus.forces, dftbplus.charges)
    result = calc.execute(water)

    assert result.success
    assert list(result.context.input_files) == [INPUT_FILE]
    assert sorted(result.context.files) == ["detailed.out", "dftb.out", "results.tag"]
    # The stub read the input AMAC wrote, and the Prefix taken from BASIS.
    log = (result.context.directory / "dftb.out").read_text()
    assert f"{len(water)} atoms" in log
    assert str(dftbp_configured) in log
    # Handlers convert the program units to the ASE ones.
    assert result.properties["energy"] == pytest.approx(STUB_ENERGY * Hartree)
    assert result.properties["forces"] == pytest.approx(
        np.asarray(stub_forces(len(water))) * (Hartree / Bohr)
    )
    assert result.properties["charges"] == pytest.approx(stub_charges(len(water)))


def test_stub_writes_a_moved_geometry_when_asked(stub_calc, water):
    """``geo_end.gen`` holds the geometry of the input, moved by a fixed step."""
    calc = stub_calc(
        stub={"files": ("detailed.out", "results.tag", "geo_end.gen")},
        module="GEOMETRY_OPTIMISATION",
    )
    calc.handler_properties(dftbplus.final_geometry)
    result = calc.execute(water)

    geometry = result.properties["final_geometry"]
    assert geometry.get_chemical_symbols() == water.get_chemical_symbols()
    assert geometry.positions == pytest.approx(water.positions + STUB_DISPLACEMENT)


@pytest.mark.parametrize("code", [1, 3])
def test_stub_failure_is_reported_as_a_failed_run(stub_calc, water, code):
    """A non-zero exit code is a failed run, with the stub log kept."""
    calc = stub_calc(stub={"return_code": code, "stderr": "stub failure\n"},
                     raise_on_error=False)
    result = calc.execute(water)

    assert not result.success
    assert result.context.return_code == code


def test_stub_uses_the_interpreter_running_the_tests(dftbp_stub):
    """The shebang points at the current interpreter: no dependency on PATH."""
    assert dftbp_stub().read_text().splitlines()[0] == f"#!{sys.executable}"


def test_stub_can_write_no_output_at_all(stub_calc, water):
    """``files=()``: the run succeeds but the handlers find nothing to read."""
    calc = stub_calc(stub={"files": ()})
    calc.handler_properties(dftbplus.energy)
    result = calc.execute(water)

    assert result.success
    assert list(result.context.files) == ["dftb.out"]
    assert "energy" not in result.properties
    assert "detailed.out" in str(result.errors[0])
