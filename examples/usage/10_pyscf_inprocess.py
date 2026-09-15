"""PySCF in process: no input file, no executable, native objects in ``ctx.objects``.

Illustrative: requires the real software, their handlers and composers, not
implemented yet.

The calculation is described exactly as for ORCA or Gaussian; only ``software``
changes. The run directory is still created, and the PySCF logs are captured in
``result.context.stdout``.
"""

from pathlib import Path

from ase.build import molecule

from amac import AMAC
from amac.assets import pyscf as pyscf_handlers

WORKDIR = Path.home() / "amac-runs" / "10-pyscf"


def main() -> None:
    """Run a B3LYP single point in the current process."""
    calc = AMAC(
        software="PYSCF",
        method="DFT",
        method_args={"variant": "B3LYP"},
        parameters={"BASIS": "cc-pVDZ"},
        cpu=4,
        workdir=WORKDIR,
        label="water-pyscf",
    )
    calc.handler_properties(
        pyscf_handlers.energy,
        pyscf_handlers.mo_energies,
        ("converged", lambda ctx: bool(ctx.objects["mf"].converged)),
    )
    result = calc.execute(molecule("H2O"))
    print(result.properties["energy"], result.properties["converged"])
    print(result.context.stdout[-500:])  # journal PySCF capturé
    print(type(result.context.objects["mf"]).__name__)  # objet natif, ex. RKS


if __name__ == "__main__":
    main()
