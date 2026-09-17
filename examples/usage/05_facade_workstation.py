"""Configure a workstation once, then use the module facade.

Illustrative: requires the real software, their handlers and composers, not
implemented yet.

``amac.configure`` only affects ``amac.calculator`` / ``amac.run``. Priority: global
defaults < per-software defaults < keyword arguments of ``calculator``; this holds
for ``validate`` too. Executables: explicit ``executable=`` > ``configure`` >
environment variable (``ORCA_EXECUTABLE``, ``GAUSSIAN_EXECUTABLE``, ...) >
``~/.config/amac/config.toml`` (or ``$AMAC_CONFIG``). AMAC never searches ``PATH``:
give absolute paths; ``amac.which("ORCA")`` shows the one used. The facade state is
global and not thread-safe.
"""

from pathlib import Path

from ase.build import molecule

import amac
from amac.assets import demonnano, gaussian, orca

PARAMETERS = {
    "method": "DFT",
    "method_args": {"variant": "PBE0"},
    "parameters": {"BASIS": "def2-SVP"},
}


def configure_workstation() -> None:
    """Defaults of this machine, for every software, then per software."""
    amac.configure(
        cpu=8,
        ram=16000,
        workdir=Path.home() / "scratch" / "amac",
        validate="warn",  # avertir plutôt que refuser, sur ce poste
    )
    amac.configure(
        software="ORCA",
        executable="/opt/orca-6.1.0/orca",
        driver="auto",  # OPI si installé, sinon le chemin AMAC
        timeout=3600,
    )
    amac.configure(software="GAUSSIAN", executable="/opt/g16/g16", ram=32000)
    # deMonNano runs in process through the deMonPy library, which starts this
    # binary itself: the executable is still configured here, like the others.
    amac.configure(software="deMonNano", executable="/opt/demon-nano/deMon.x")


def main() -> None:
    """Create calculators with the facade and run them."""
    configure_workstation()
    water = molecule("H2O")

    # Calculateur courant : ORCA, 8 cœurs et driver "auto" venant de configure().
    orca_calc = amac.calculator(
        parameters=PARAMETERS,
        platform="ORCA",
        label="water-orca",
        handlers=[orca.energy],
    )
    print(f"ORCA driver: {orca_calc.driver.name} ({orca_calc.driver.fallback})")
    print(amac.run(water).properties)

    # Handlers pour cet appel seulement ; ceux du calculateur sont restaurés.
    detailed = amac.run(
        water,
        handlers=[orca.energy, orca.dipole, orca.charges],
        label="water-orca-detailed",
    )
    print(sorted(detailed.properties), [meta.name for meta in orca_calc.handlers])

    # Gaussian devient le calculateur courant ; cpu=4 et validate="strict"
    # l'emportent sur configure().
    amac.calculator(
        parameters=PARAMETERS,
        platform="GAUSSIAN",
        label="water-gaussian",
        cpu=4,
        validate="strict",
        handlers=[gaussian.energy],
    )
    print(amac.run(water).properties)
    print(amac.run(water, calc=orca_calc, label="water-orca-again").properties)

    # deMonNano en DFTB, avec l'exécutable configuré plus haut. Les fichiers
    # Slater-Koster sont obligatoires, et les forces exigent la directive
    # PRINT GRAD : AMAC n'ajoute rien de lui-même.
    amac.calculator(
        parameters={
            "method": "DFTB",
            "method_args": {"variant": "DFTB2"},
            "parameters": {
                "SLATER_KOSTER_FILES": {
                    "PTYPE": "BIO",
                    "SKFILE": "/opt/demon-nano/basis",
                },
                "OUTPUT_CONTROL": {"GRAD": True},
            },
        },
        platform="deMonNano",
        label="water-demon",
        handlers=[demonnano.energy, demonnano.forces],
    )
    print(amac.run(water).properties)

    amac.reset_configuration()


if __name__ == "__main__":
    main()
