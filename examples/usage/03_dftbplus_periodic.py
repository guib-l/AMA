"""DFTB+ on a periodic silicon crystal: cell, pbc, k-points, charges and forces.

Illustrative: requires the real software, their handlers and composers, not
implemented yet.

Method, module and parameter names come from ``amac/assets/dftbplus/doc.json``:
the ``DFTB2`` variant imposes ``SCC = Yes`` (``SETS``), ``SLATER_KOSTER_FILES`` and
``KPOINTS`` are parameters with variants, and ``Temperature`` is a common argument of
every ``FILLING`` choice. The ``PERIODIC`` rules are checked at ``execute()`` against
``atoms.pbc``: the transport module (alias ``NEGF``) only accepts periodic systems.
Values are written in DFTB+ units (no conversion).
"""

from pathlib import Path

import numpy as np
from ase.build import bulk, molecule

import amac
from amac import AMAC
from amac.assets import dftbplus

WORKDIR = Path.home() / "amac-runs" / "03-dftbplus"

TIGHT_BINDING = {
    "method": "TIGHT_BINDING",
    # DFTB2 impose SCC = Yes : inutile de l'écrire.
    "method_args": {
        "variant": "DFTB2",
        "SCCTolerance": 1e-6,
        "MaxAngularMomentum": {"Si": "p"},
    },
}

PARAMETERS = {
    "SLATER_KOSTER_FILES": {
        "variant": "Type2FileNames",
        "Prefix": "pbc-0-3/",
        "Separator": "-",
        "Suffix": ".skf",
    },
    # Monkhorst-Pack 4x4x4 décalé : 9 entiers puis le décalage.
    "KPOINTS": {
        "SupercellFolding": [[4, 0, 0], [0, 4, 0], [0, 0, 4], [0.5, 0.5, 0.5]]
    },
    "FILLING": {"Fermi": {"Temperature": 0.001}},  # Hartree
    "MIXER": {"Broyden": {"MixingParameter": 0.1}},
    "OPTIONS": {"WriteResultsTag": True},
    "ANALYSIS": {"MullikenAnalysis": True},
}


def main() -> None:
    """Run a silicon supercell, then show the PERIODIC check on a molecule."""
    crystal = bulk("Si", "diamond", a=5.431, cubic=True)  # pbc = (True, True, True)
    crystal.rattle(stdev=0.02, seed=1)  # forces non nulles

    calc = AMAC(
        platform="DFTB+",
        module="SINGLE_POINT",
        parameters=PARAMETERS,
        cpu=8,
        workdir=WORKDIR,
        label="si-diamond",
        **TIGHT_BINDING,
    )
    calc.handler_properties(dftbplus.energy, dftbplus.forces, dftbplus.charges)
    result = calc.execute(crystal)

    forces = np.asarray(result.properties["forces"])
    charges = np.asarray(result.properties["charges"])
    print(f"Energy: {result.properties['energy']:.6f} Eh")
    print(f"Max |F|: {np.abs(forces).max():.4e}, sum of forces: {forces.sum(axis=0)}")
    print(f"Mulliken charges: min {charges.min():+.4f}, max {charges.max():+.4f}")

    # Vérification PERIODIC : le transport (NEGF) exige une géométrie périodique.
    transport = AMAC(
        platform="DFTB+",
        module="NEGF",
        parameters=PARAMETERS,
        workdir=WORKDIR,
        label="negf-on-a-molecule",
        **TIGHT_BINDING,
    )
    try:
        transport.execute(molecule("SiH4"))
    except amac.ValidationError as error:
        print(f"Refused before any run:\n{error}")


if __name__ == "__main__":
    main()
