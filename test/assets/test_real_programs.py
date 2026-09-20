"""Runs of the real programs, when this machine is configured for them.

Every test here is marked ``real`` and skipped unless a configuration file gives
the executable and ``BASIS`` of the software: ``--amac-config=PATH``, else the
``config-amac.json`` of the repository. Nothing is discovered, and no environment
variable is read: what the file does not give, the test skips.

Run them with::

    pytest -m real                                  # config-amac.json of the repository
    pytest -m real --amac-config=/path/to/config-amac.json

The reference energies below were measured through AMAC on the H2O geometry of
ASE with the programs of this machine (TODO-4, step 0); they pin the chain, not
the physics, so a different build or parameter set changes them.
"""

import numpy as np
import pytest
from ase.build import molecule

from amac import AMAC
from amac.assets import demonnano, dftbplus

pytestmark = pytest.mark.real

# Energies in eV, for H2O at the ASE geometry.
DFTBP_ENERGY = -110.960395
DEMON_ENERGY = -110.885009
TOLERANCE = 1e-4

DFTBPLUS_SINGLE_POINT = {
    "software": "DFTB+",
    "method": "TIGHT_BINDING",
    "method_args": {
        "variant": "DFTB2",
        "SCCTolerance": 1e-6,
        "MaxAngularMomentum": {"O": "p", "H": "s"},
    },
    "module": "SINGLE_POINT",
    "parameters": {
        "SLATER_KOSTER_FILES": {"variant": "Type2FileNames"},
        "ANALYSIS": {"MullikenAnalysis": True, "Printforces": True},
        "OPTIONS": {"WriteResultsTag": True},
    },
}

DEMONNANO_SINGLE_POINT = {
    "software": "deMonNano",
    "method": "TIGHT_BINDING",
    "method_args": {"variant": "DFTB2"},
    "module": "SINGLE_POINT",
    "parameters": {
        "SLATER_KOSTER_FILES": {"PTYPE": "BIO"},
        "CHARGE": 0,
        "MULTIPLICITY": 1,
        "OUTPUT_CONTROL": {"GRAD": True},
    },
}


def test_dftbplus_single_point(tmp_path, real_software):
    """DFTB+ writes its input, runs, and the handlers read eV and charges back."""
    real_software("DFTB+")
    calc = AMAC(**DFTBPLUS_SINGLE_POINT, workdir=tmp_path, label="water")
    calc.handler_properties(dftbplus.energy, dftbplus.forces, dftbplus.charges)
    result = calc.execute(molecule("H2O"))

    assert result.success, result.errors
    assert result.properties["energy"] == pytest.approx(DFTBP_ENERGY, abs=TOLERANCE)
    charges = np.asarray(result.properties["charges"])
    assert charges.shape == (3,)
    assert charges[0] < 0 < charges[1]  # the oxygen carries the negative charge
    assert charges.sum() == pytest.approx(0.0, abs=1e-6)
    assert np.asarray(result.properties["forces"]).shape == (3, 3)
    assert sorted(result.context.input_files) == ["dftb_in.hsd"]
    assert {"detailed.out", "dftb.out"} <= set(result.context.files)


def test_dftbplus_optimisation_lowers_the_energy(tmp_path, real_software):
    """A geometry optimisation moves the atoms and ends below the single point."""
    real_software("DFTB+")
    spec = {
        **DFTBPLUS_SINGLE_POINT,
        "module": "OPT",
    }
    calc = AMAC(**spec, workdir=tmp_path, label="water-opt")
    calc.handler_properties(
        dftbplus.energy, dftbplus.forces, dftbplus.final_geometry
    )
    result = calc.execute(molecule("H2O"))

    assert result.success, result.errors
    assert result.properties["energy"] <= DFTBP_ENERGY + TOLERANCE
    optimised = result.properties["final_geometry"]
    assert optimised.get_chemical_symbols() == ["O", "H", "H"]
    assert np.abs(np.asarray(result.properties["forces"])).max() < 1e-2  # eV/A


def test_demonnano_single_point(tmp_path, real_software):
    """deMonNano runs in process through deMonPy and gives the same quantities."""
    real_software("deMonNano")
    calc = AMAC(**DEMONNANO_SINGLE_POINT, workdir=tmp_path, label="water")
    calc.handler_properties(demonnano.energy, demonnano.charges)
    result = calc.execute(molecule("H2O"))

    assert result.success, result.errors
    assert result.properties["energy"] == pytest.approx(DEMON_ENERGY, abs=TOLERANCE)
    charges = np.asarray(result.properties["charges"])
    assert charges.shape == (3,)
    assert charges[0] < 0 < charges[1]
    # An in-process software writes no input file and returns no exit code.
    assert result.context.input_files == {}
    assert result.context.return_code is None


def test_both_programs_agree_on_the_sign_of_the_charges(tmp_path, real_software):
    """The same specification, two programs, the same physical picture."""
    real_software("DFTB+")
    real_software("deMonNano")
    energies = {}
    for spec, handlers in (
        (DFTBPLUS_SINGLE_POINT, (dftbplus.energy, dftbplus.charges)),
        (DEMONNANO_SINGLE_POINT, (demonnano.energy, demonnano.charges)),
    ):
        calc = AMAC(**spec, workdir=tmp_path, label=spec["software"].lower())
        calc.handler_properties(*handlers)
        result = calc.execute(molecule("H2O"))
        assert result.success, result.errors
        energies[spec["software"]] = result.properties["energy"]
        assert np.asarray(result.properties["charges"])[0] < 0

    # Both handlers return eV: the gap is between the programs, not the units.
    assert abs(energies["DFTB+"] - energies["deMonNano"]) < 1.0
