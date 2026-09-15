"""Handlers: custom handlers reading output files, failures, requires_files.

Illustrative: requires the real software, their handlers and composers, not
implemented yet.

A failing handler, or one whose ``requires_files`` match no produced file, has no
entry in ``result.properties``. With ``handler_errors="collect"`` (default) its
``HandlerError`` goes to ``result.errors``; with ``"raise"`` the first one is raised.
``result.success`` only reflects the run.
"""

import re
from pathlib import Path

from ase.build import molecule

import amac
from amac import AMAC
from amac.assets import orca
from amac.engine.handlers import handler

WORKDIR = Path.home() / "amac-runs" / "07-handlers"

CALCULATION = {
    "software": "ORCA",
    "method": "DFT",
    "method_args": {"variant": "B3LYP"},
    "parameters": {"BASIS": "def2-SVP"},
    "workdir": WORKDIR,
}


@handler(requires_files=("orca.out",))  # sans logiciel : accepté par tous
def scf_cycles(ctx) -> int:
    """Custom handler: number of SCF cycles read in the ORCA output."""
    text = ctx.files["orca.out"].read_text(encoding="utf-8")
    return int(re.search(r"SCF CONVERGED AFTER\s+(\d+)\s+CYCLES", text).group(1))


def run_time(ctx) -> str:
    """Plain custom handler, without metadata."""
    text = ctx.files["orca.out"].read_text(encoding="utf-8")
    return re.search(r"TOTAL RUN TIME: (.+)", text).group(1).strip()


def main() -> None:
    """Collect handler failures, then raise the first one."""
    water = molecule("H2O")

    # collect : les échecs sont enregistrés, les autres propriétés sont calculées.
    calc = AMAC(label="collect", **CALCULATION)
    calc.handler_properties(
        orca.energy,
        scf_cycles,
        run_time,
        ("broken", lambda ctx: ctx.objects["not-there"]),  # KeyError
        orca.hessian,  # requires_files=("*.hess",) : absent en single point
    )
    result = calc.execute(water)
    print(result.success, sorted(result.properties))
    for error in result.errors:
        print(f"  {error.handler}: {error} (missing: {error.missing_files})")

    # modules= : un handler de fréquences est refusé pour un single point.
    try:
        calc.handler_properties(orca.frequencies)
    except ValueError as error:
        print(error)

    # raise : le premier échec interrompt execute(), exception d'origine chaînée.
    strict = AMAC(label="raise", handler_errors="raise", **CALCULATION)
    strict.handler_properties(orca.energy, ("broken", lambda ctx: 1 / 0))
    try:
        strict.execute(water)
    except amac.HandlerError as error:
        print(f"{error} <- {error.__cause__!r}")


if __name__ == "__main__":
    main()
