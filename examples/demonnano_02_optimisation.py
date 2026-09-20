"""deMon-Nano: geometry optimisation, then a short molecular dynamics.

Runs deMon-Nano when it is configured (see ``common_01_executables.py``);
otherwise it stops with what to set. It also needs the ``deMonPy`` library
(``DeMonNanoPy``, installed from its repository).

The two runs share the same method and the same parameters: only ``module`` and
``module_args`` change, which is what the modules of the catalog are for. Both
modules of deMon-Nano are declared ``MOLECULE``: a periodic geometry is refused
by the validation, before anything runs.
"""

import logging
import sys
from pathlib import Path

import numpy as np
from ase.build import molecule

import amac
from amac import AMAC
from amac.assets import demonnano

CONFIG_OPTION = "--config="  # configuration file handed to AMAC
PROJECT_CONFIG = Path(__file__).resolve().parents[1] / "config-amac.json"
DEFAULT_RUNS = Path.home() / "amac-runs"
RUNS_NAME = "demonnano-optimisation"


def config_file() -> Path:
    """Return the configuration file of this run.

    ``--config=PATH`` wins, else the ``config-amac.json`` of this repository.
    AMAC reads no environment variable: the file is handed to it explicitly.
    """
    for argument in sys.argv[1:]:
        if argument.startswith(CONFIG_OPTION):
            return Path(argument.removeprefix(CONFIG_OPTION)).expanduser()
    return PROJECT_CONFIG


def workdir() -> Path:
    """Return where this example writes: its input, its output, nothing else.

    The first argument that is not an option wins, else ``~/amac-runs``. AMAC
    reads no environment variable for this: the directory chosen here is handed
    to it as ``workdir=``, which the ``workdir`` of the configuration file would
    also give.
    """
    given = next((arg for arg in sys.argv[1:] if not arg.startswith("-")), None)
    return Path(given or DEFAULT_RUNS).expanduser() / RUNS_NAME


# Canonical part, shared by the two runs below.
LEVEL_OF_THEORY = {
    "software": "deMonNano",
    "method": "TIGHT_BINDING",
    "method_args": {"variant": "DFTB2"},
    "parameters": {
        "SLATER_KOSTER_FILES": {"PTYPE": "BIO"},
        "CHARGE": 0,
        "MULTIPLICITY": 1,
        "OUTPUT_CONTROL": {"GRAD": True},
    },
}

OPTIMISATION = {
    **LEVEL_OF_THEORY,
    "module": "OPT",  # alias of GEOMETRY_OPTIMISATION
    "module_args": {"MAX": 100},
}

DYNAMICS = {
    **LEVEL_OF_THEORY,
    "module": "MD",  # alias of MOLECULAR_DYNAMICS
    "module_args": {"STEPS": 20, "TEMPERATURE": 300.0},
}

SPECS = (OPTIMISATION, DYNAMICS)

# A periodic cell with MOLECULE-only modules: refused by the validation.
INVALID_SPECS = ()


def require(software: str) -> None:
    """Give AMAC the configuration file, or stop with the command to run.

    AMAC reads no environment variable and never searches ``PATH``: the file of
    :func:`config_file` is handed to ``amac.set_config`` and must give the
    executable of ``software``.
    """
    config = config_file()
    command = f"python {sys.argv[0]} {CONFIG_OPTION}/path/to/config-amac.json"
    if not config.is_file():
        raise SystemExit(
            f"No configuration file {config}.\nWrite one and run:\n  {command}\n"
            "(see examples/common_01_executables.py for its format)."
        )
    amac.set_config(config)
    if amac.which(software) is None:
        raise SystemExit(
            f"No executable for {software} in {config}: give it as "
            f'"software" -> "{software}" -> "executable".\n  {command}'
        )


def optimise(root: Path) -> object:
    """Optimise water and return the geometry the library converged to."""
    calc = AMAC(
        **OPTIMISATION,
        workdir=root,
        label="water-opt",
        keep_files=True,
        overwrite=True,  # so that the example can be run again
    )
    calc.handler_properties(
        demonnano.energy, demonnano.forces, demonnano.final_geometry
    )
    result = calc.execute(molecule("H2O"))
    if not result.success:
        raise SystemExit(f"deMon-Nano failed: {result.errors}")

    optimised = result.properties["final_geometry"]
    print(f"Energy: {result.properties['energy']:.6f} eV")
    # A handler returns None when the program wrote nothing for it: deMon-Nano
    # does not print the gradient of an optimisation, only the final geometry.
    forces = result.properties["forces"]
    if forces is None:
        print("Forces: not written by the program for this module")
    else:
        print(f"Residual |F|: {np.abs(np.asarray(forces)).max():.2e} eV/A")
    print(f"O-H: {optimised.get_distance(0, 1):.4f} A")
    return optimised


def run_dynamics(start, root: Path) -> None:
    """Run a short dynamics from the optimised geometry."""
    calc = AMAC(
        **DYNAMICS,
        workdir=root,
        label="water-md",
        keep_files=True,
        overwrite=True,
    )
    calc.handler_properties(demonnano.energy)
    result = calc.execute(start)
    if not result.success:
        raise SystemExit(f"deMon-Nano failed: {result.errors}")
    # The dynamics runs, but its log carries no final energy where the parser
    # looks for one: the handler then returns None rather than inventing a value.
    energy = result.properties["energy"]
    print(f"Energy after the dynamics: {energy if energy is None else f'{energy:.6f} eV'}")
    print(f"files: {sorted(result.context.files)} in {result.context.directory}")


def show_workdir(root: Path) -> None:
    """Print where the files go, and let AMAC log each run directory."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    print(f"workdir: {root}")


def main() -> None:
    """Optimise, then run the dynamics from the optimised geometry."""
    require("deMonNano")
    root = workdir()
    show_workdir(root)
    run_dynamics(optimise(root), root)


if __name__ == "__main__":
    main()
