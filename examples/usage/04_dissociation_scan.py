"""Dissociation curve of H2: one image per distance, failed images kept.

Illustrative: requires the real software, their handlers and composers, not
implemented yet.

With ``raise_on_error=False`` a failing image (SCF not converged, timeout, ...) gives
a ``Result(success=False)`` and the scan goes on. Long distances get more SCF
iterations through per-image overrides. The results are stored, reloaded with
``amac.load``, analysed with numpy, and a forgotten property is extracted afterwards
with ``amac.reprocess``, without running the calculations again.
"""

from pathlib import Path

import numpy as np
from ase import Atoms, units

import amac
from amac import AMAC
from amac.assets import orca

WORKDIR = Path.home() / "amac-runs" / "04-scan"
DISTANCES = np.linspace(0.5, 3.0, 26)  # Angstrom


def h2(distance: float) -> Atoms:
    """Return H2 with its bond along z."""
    return Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.0, 0.0, distance]])


def image(distance: float):
    """Return an image; beyond 2 Angstrom, the SCF gets more iterations."""
    if distance <= 2.0:
        return h2(distance)
    return h2(distance), {"parameters": {"SCF": {"MaxIter": 800}}}


def main() -> None:
    """Scan the bond length, then analyse the reloaded curve."""
    calc = AMAC(
        software="ORCA",
        method="DFT",
        method_args={"variant": "B3LYP", "Multiplicity": 1},
        parameters={"BASIS": "def2-TZVP", "SCF": {"MaxIter": 300}},
        cpu=2,
        timeout=900,
        raise_on_error=False,  # une image en échec n'arrête pas le balayage
        workdir=WORKDIR,
        label="h2-scan",
    )
    calc.handler_properties(orca.energy)
    results = calc.execute([image(distance) for distance in DISTANCES])

    for distance, result in zip(DISTANCES, results, strict=True):
        if not result.success:
            print(f"d = {distance:.2f} A failed: {result.errors[0]}")

    path = calc.store(WORKDIR / "h2-scan")

    # Relecture : erreurs en dicts, géométrie reconstruite, spec effective par image.
    reloaded = amac.load(path)
    ok = [result for result in reloaded if result.success]
    for result in reloaded:
        for error in result.errors:
            print(f"image {result.provenance['image']}: {error['type']}")

    distances = np.array([r.provenance["atoms"].get_distance(0, 1) for r in ok])
    energies = np.array([r.properties["energy"] for r in ok]) * units.Hartree  # eV
    minimum = int(np.argmin(energies))
    print(f"{len(ok)}/{len(reloaded)} images converged")
    print(f"r_e ~ {distances[minimum]:.3f} A")
    print(f"D_e ~ {energies[-1] - energies[minimum]:.3f} eV (last point as reference)")

    # Propriété oubliée : charges relues dans les fichiers du minimum, sans relancer.
    charges = amac.reprocess(ok[minimum], [orca.charges]).properties["charges"]
    print(f"Charges at the minimum: {charges}")


if __name__ == "__main__":
    main()
