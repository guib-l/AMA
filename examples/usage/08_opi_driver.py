"""ORCA with its dedicated library, OPI (``pip install orca-pi``, ORCA >= 6.1).

Illustrative: requires the real software, their handlers and composers, not
implemented yet.

- ``driver="opi"`` requires the library: ``amac.DriverUnavailableError`` otherwise;
- ``driver="auto"`` uses OPI when it can, otherwise the AMAC path, and records why in
  ``provenance["driver_fallback"]``;
- handlers reading OPI objects declare ``drivers=("opi",)``: they are refused on the
  AMAC path, or discarded with ``skip_incompatible=True``.
"""

from pathlib import Path

from ase.build import molecule

import amac
from amac import AMAC
from amac.assets import orca

WORKDIR = Path.home() / "amac-runs" / "08-opi"

CALCULATION = {
    "software": "ORCA",
    "method": "DFT",
    "method_args": {"variant": "r2SCAN-3c"},
    "parameters": {"SCF": {"Convergence": "Tight"}},
    "cpu": 4,
    "workdir": WORKDIR,
}


def main() -> None:
    """Request OPI explicitly, then let AMAC choose."""
    water = molecule("H2O")

    # Explicite : erreur claire, avec la commande pip, si OPI est absent.
    try:
        explicit = AMAC(driver="opi", label="opi", **CALCULATION)
    except amac.DriverUnavailableError as error:
        print(error)
    else:
        explicit.handler_properties(orca.energy, orca.opi_output)
        output = explicit.execute(water).properties["opi_output"]
        print(f"Native OPI output: {type(output).__name__}")

    # auto : OPI si disponible, sinon repli à la sélection (jamais pendant le run).
    # « OPI si disponible, sinon handlers fichiers » : sans try/except.
    calc = AMAC(driver="auto", label="auto", **CALCULATION)
    calc.handler_properties(
        orca.energy, orca.dipole, orca.opi_output, skip_incompatible=True
    )
    result = calc.execute(water)
    provenance = result.provenance
    print(f"driver={provenance['driver']} version={provenance['driver_version']}")
    print(f"fallback={provenance['driver_fallback']}")
    print(sorted(result.properties))

    # Chemin AMAC : sans skip_incompatible, un handler drivers=("opi",) est refusé.
    try:
        AMAC(driver="amac", **CALCULATION).handler_properties(orca.opi_output)
    except ValueError as error:
        print(error)


if __name__ == "__main__":
    main()
