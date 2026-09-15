"""Geometry optimisation, then frequencies on the optimised geometry, with ORCA.

Illustrative: requires the real software, their handlers and composers, not
implemented yet.

Calculations are not chained automatically: the optimised geometry is extracted by a
handler of the first calculation and given to the second one.
"""

from pathlib import Path

import numpy as np
from ase.build import molecule

from amac import AMAC
from amac.assets import orca
from amac.ios.store import store_results

WORKDIR = Path.home() / "amac-runs" / "02-opt-freq"

LEVEL_OF_THEORY = {
    "method": "DFT",
    "method_args": {"variant": "B3LYP"},
    "parameters": {"BASIS": "def2-SVP", "DISPERSION": "D3BJ"},
}


def main() -> None:
    """Optimise formaldehyde, then check that the optimised geometry is a minimum."""
    # 1. Optimisation : le handler final_geometry renvoie un ase.Atoms.
    optimisation = AMAC(
        software="ORCA",
        module="OPT",
        module_args={"Convergence": "Tight"},
        cpu=4,
        workdir=WORKDIR,
        label="formaldehyde-opt",
        **LEVEL_OF_THEORY,
    )
    optimisation.handler_properties(orca.energy, orca.final_geometry)
    opt_result = optimisation.execute(molecule("H2CO"))
    optimised = opt_result.properties["final_geometry"]
    print(f"Optimised energy: {opt_result.properties['energy']:.8f} Eh")

    # 2. Fréquences au même niveau de théorie, sur la géométrie optimisée.
    frequencies = AMAC(
        software="ORCA",
        module="FREQ",
        cpu=4,
        workdir=WORKDIR,
        label="formaldehyde-freq",
        **LEVEL_OF_THEORY,
    )
    frequencies.handler_properties(orca.energy, orca.frequencies)
    freq_result = frequencies.execute(optimised)

    wavenumbers = np.asarray(freq_result.properties["frequencies"])  # cm-1
    imaginary = wavenumbers[wavenumbers < 0.0]
    print(f"Frequencies (cm-1): {np.round(wavenumbers, 1)}")
    print("Minimum" if imaginary.size == 0 else f"Imaginary modes: {imaginary}")

    # Les deux résultats dans un seul fichier, avec leur provenance.
    path = store_results([opt_result, freq_result], WORKDIR / "formaldehyde")
    print(f"Stored in {path}")


if __name__ == "__main__":
    main()
