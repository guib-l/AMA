"""Validation modes and raw keywords with ORCA.

Illustrative: requires the real software, their handlers and composers, not
implemented yet.

- ``validate="strict"`` (default) raises one ``amac.ValidationError`` listing every
  issue, and refuses a software without ``doc.json``;
- ``validate="warn"`` emits warnings and keeps the issues in ``calc.issues``;
- ``raw`` passes ORCA keywords unchanged, never validated;
- geometry-dependent rules (``PERIODIC``) are checked at ``execute()``.
"""

import warnings
from pathlib import Path

from ase.build import molecule

import amac
from amac import AMAC
from amac.assets import orca

WORKDIR = Path.home() / "amac-runs" / "06-validation"


def main() -> None:
    """Show strict and warn modes, raw keywords and the periodicity check."""
    # 1. strict : toutes les erreurs sont rassemblées dans un seul message.
    try:
        AMAC(
            software="ORCA",
            method="DFT",
            method_args={"variant": "B3LYPP"},  # variante inconnue
            parameters={"BASIS": "def2-SVP", "SCF": {"MaxIter": 0}},  # hors RANGE
            workdir=WORKDIR,
        )
    except amac.ValidationError as error:
        print(error)

    # 2. warn : le calcul est créé, les problèmes restent consultables.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        lenient = AMAC(
            software="ORCA",
            method="DFT",
            method_args={"variant": "B3LYP"},
            parameters={"BASIS": "def2-SVP", "SCF": {"MaxIter": 5000}},
            validate="warn",
            workdir=WORKDIR,
            label="lenient",
        )
    print(f"{len(caught)} warning(s), validated={lenient.validated}")
    for issue in lenient.issues:
        print(f"  {issue.level} {issue.path}: {issue.message}")

    # 3. raw : mots-clés ORCA non décrits dans doc.json, transmis tels quels.
    calc = AMAC(
        software="ORCA",
        method="DFT",
        method_args={"variant": "B3LYP"},
        parameters={"BASIS": "def2-TZVP"},
        raw=["! RIJCOSX def2/J TightSCF", "%output Print[P_Hirshfeld] 1 end"],
        workdir=WORKDIR,
        label="raw-keywords",
    )
    calc.handler_properties(orca.energy)
    water = molecule("H2O")
    print(calc.execute(water).properties)

    # 4. PERIODIC : ORCA moléculaire refuse une géométrie périodique, avant le run.
    periodic = water.copy()
    periodic.cell = [10.0, 10.0, 10.0]
    periodic.pbc = True
    try:
        calc.execute(periodic, label="periodic-water")
    except amac.ValidationError as error:
        print(error)


if __name__ == "__main__":
    main()
