"""Same DFT single point with ORCA, then with Gaussian, changing only the software.

Illustrative: requires the programs themselves. The ORCA package is written; the
Gaussian one is not yet.

The calculation is described once; only ``software`` (and the handler module, since
handlers belong to a software) changes between the two runs. Handlers return ASE
units, so both energies come back in eV.
"""

from pathlib import Path

from ase import Atoms, units

from amac import AMAC
from amac.assets import gaussian, orca

WORKDIR = Path.home() / "amac-runs" / "01-single-point"

# Description canonique du calcul, commune aux deux logiciels.
# La charge et la multiplicité sont des paramètres, pas des arguments de méthode.
CALCULATION = {
    "method": "DFT",
    "method_args": {"variant": "PBE0"},
    "module": "SINGLE_POINT",
    "parameters": {
        "BASIS": "def2-TZVP",
        "CHARGE": 0,
        "MULTIPLICITY": 1,
        "DISPERSION": "D3BJ",
        "SCF": {"Convergence": "Tight"},
    },
}

# Les handlers appartiennent à un logiciel : un module par logiciel.
HANDLERS = {
    "ORCA": (orca.energy, orca.dipole),
    "GAUSSIAN": (gaussian.energy, gaussian.dipole),
}


def water() -> Atoms:
    """Return a water molecule (Angstrom)."""
    positions = [[0.0, 0.0, 0.1173], [0.0, 0.7572, -0.4692], [0.0, -0.7572, -0.4692]]
    return Atoms("OH2", positions=positions)


def main() -> None:
    """Run the same single point with both programs and compare the energies."""
    energies = {}
    for software, handlers in HANDLERS.items():
        calc = AMAC(
            software=software,
            cpu=4,
            ram=8000,
            workdir=WORKDIR,
            label=f"water-{software.lower()}",
            **CALCULATION,
        )
        calc.handler_properties(*handlers)
        result = calc.execute(water())
        if not result.success:
            raise SystemExit(f"{software} failed: {result.errors}")
        energies[software] = result.properties["energy"]
        print(f"{software:8s} E = {energies[software]:.8f} eV")
        print(f"{software:8s} dipole = {result.properties['dipole']}")

    # Écart entre les deux programmes, en kcal/mol : les handlers rendent des eV.
    difference = (energies["ORCA"] - energies["GAUSSIAN"]) / (units.kcal / units.mol)
    print(f"ORCA - Gaussian = {difference:+.4f} kcal/mol")


if __name__ == "__main__":
    main()
