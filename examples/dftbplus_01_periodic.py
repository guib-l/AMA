"""DFTB+ on a periodic carbon crystal: cell, k-points, charges and forces.

Runs DFTB+ when it is configured (see ``common_01_executables.py``);
otherwise it stops with what to set.

Every name comes from ``amac/assets/dftbplus/doc.json``: the ``DFTB2`` variant sets
``SCC = Yes`` by itself, ``SLATER_KOSTER_FILES`` is mandatory, and ``KPOINTS``,
``SMEARING`` and ``MIXER`` are choices written as ``{"<variant>": {...}}``;
``SMEARING`` also takes a bare temperature, filled into its default choice. Its
modules are ``PERIODIC = BOTH``: the same specification runs on a crystal and on a
molecule, only ``KPOINTS`` is bound to a periodic cell (``CONDITION`` ``Periodic =
Yes``). Input values are in atomic units (Hartree, Bohr), as the ``doc.json``
declares; the handlers return ASE units (eV, eV/A, e).

The directory of the Slater-Koster files is never in the spec: AMAC writes
``Prefix`` from ``BASIS`` in the ``env`` of DFTB+ in ``config-amac.json``. The
crystal here is diamond carbon, so that the organic ``mio-1-1`` set (H, C, N, O,
S, P) is enough to run it; a set made for solids, such as ``pbc-0-3``, is the
right one for a real study.
"""

import logging
import sys
from pathlib import Path

import numpy as np
from ase.build import bulk

import amac
from amac import AMAC
from amac.assets import dftbplus

CONFIG_OPTION = "--config="  # configuration file handed to AMAC
PROJECT_CONFIG = Path(__file__).resolve().parents[1] / "config-amac.json"
DEFAULT_RUNS = Path.home() / "amac-runs"
RUNS_NAME = "dftbplus-periodic"


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


TIGHT_BINDING = {
    "software": "DFTB+",
    "method": "TIGHT_BINDING",
    "method_args": {
        "variant": "DFTB2",
        "SCCTolerance": 1e-6,
        "MaxAngularMomentum": {"C": "p"},
    },
    "module": "SINGLE_POINT",
    "parameters": {
        "SLATER_KOSTER_FILES": {
            "variant": "Type2FileNames",
        },
        # Monkhorst-Pack 4x4x4, shifted: the folding matrix then the shift.
        "KPOINTS": {
            "SupercellFolding": [[4, 0, 0], [0, 4, 0], [0, 0, 4], [0.5, 0.5, 0.5]]
        },
        # Bare value: Fermi, the default choice, at that temperature (Hartree).
        # Written out, the same thing: {"Fermi": {"Temperature": 0.001}}.
        "SMEARING": 0.001,
        "MIXER": {"Broyden": {"MixingParameter": 0.1}},
        "OPTIONS": {"WriteResultsTag": True},
        "ANALYSIS": {"MullikenAnalysis": True, "Printforces": True},
    },
}

SPECS = (TIGHT_BINDING,)


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


def show_workdir(root: Path) -> None:
    """Print where the files go, and let AMAC log each run directory."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    print(f"workdir: {root}")


def main() -> None:
    """Run a carbon supercell and read its energy, forces and charges."""
    require("DFTB+")
    root = workdir()
    show_workdir(root)
    crystal = bulk("C", "diamond", a=3.567, cubic=True)  # pbc = (True, True, True)
    crystal.rattle(stdev=0.02, seed=1)  # so that the forces are not zero

    calc = AMAC(
        **TIGHT_BINDING,
        cpu=8,
        workdir=root,
        label="c-diamond",
        overwrite=True,  # so that the example can be run again
        raise_on_error=False,  # a failed run is reported, not raised
    )
    calc.handler_properties(dftbplus.energy, dftbplus.forces, dftbplus.charges)
    result = calc.execute(crystal)
    if not result.success:
        # collect() never ran, so the log is read from the run directory itself.
        log = result.context.directory.joinpath("dftb.out")
        tail = log.read_text(encoding="utf-8")[-600:] if log.is_file() else ""
        raise SystemExit(f"DFTB+ failed: {result.errors}\n{tail}")

    forces = np.asarray(result.properties["forces"])
    charges = np.asarray(result.properties["charges"])
    print(f"Energy: {result.properties['energy']:.6f} eV")
    print(f"Max |F|: {np.abs(forces).max():.4e} eV/A, sum: {forces.sum(axis=0)}")
    print(f"Mulliken charges: min {charges.min():+.4f}, max {charges.max():+.4f}")

    # The written input keeps the atomic units of the program; ctx.input_files
    # lists what AMAC wrote, ctx.files what the run produced.
    context = result.context
    print(f"in {context.directory}:")
    print(f"  wrote {sorted(context.input_files)}, produced {sorted(context.files)}")


if __name__ == "__main__":
    main()
