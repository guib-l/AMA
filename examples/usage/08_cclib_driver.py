"""ORCA read back with cclib (``pip install cclib``) instead of the AMAC parser.

Illustrative: requires ORCA itself to produce the outputs.

- ``driver="cclib"`` requires the library: ``amac.DriverUnavailableError`` otherwise;
- ``driver="auto"`` uses cclib when it can, otherwise the AMAC path, and records why
  in ``provenance["driver_fallback"]``;
- either way the handlers are the same: a collecting driver fills the normalized
  output that ``orca.energy`` and its neighbours read.

ORCA also has a dedicated library, OPI (``orca-pi``). Its driver is not written
yet: see the placeholders P8 to P10 of TODO-3.md.
"""

from pathlib import Path

from ase.build import molecule

import amac
from amac import AMAC
from amac.assets import orca

WORKDIR = Path.home() / "amac-runs" / "08-cclib"

CALCULATION = {
    "software": "ORCA",
    "method": "DFT",
    "method_args": {"variant": "r2SCAN"},
    "parameters": {"BASIS": "def2-SVP", "SCF": {"Convergence": "Tight"}},
    "cpu": 4,
    "workdir": WORKDIR,
}


def main() -> None:
    """Request cclib explicitly, then let AMAC choose."""
    water = molecule("H2O")

    # Explicit: a clear error, with the pip command, when cclib is absent.
    try:
        explicit = AMAC(driver="cclib", label="cclib", **CALCULATION)
    except amac.DriverUnavailableError as error:
        print(error)
    else:
        explicit.handler_properties(orca.energy, orca.charges)
        result = explicit.execute(water)
        print(f"E = {result.properties['energy']:.6f} eV")
        print(f"Mulliken charges: {result.properties['charges']}")

    # auto: cclib if available, otherwise the AMAC parser. The choice is made once,
    # when the calculator is created, never during a run.
    calc = AMAC(driver="auto", label="auto", **CALCULATION)
    calc.handler_properties(orca.energy, orca.dipole, orca.orbital_energies)
    result = calc.execute(water)
    provenance = result.provenance
    print(f"driver={provenance['driver']} version={provenance['driver_version']}")
    print(f"fallback={provenance['driver_fallback']}")
    print(sorted(result.properties))


if __name__ == "__main__":
    main()
