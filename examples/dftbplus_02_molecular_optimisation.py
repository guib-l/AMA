"""DFTB+ on a molecule: DFTB3 geometry optimisation, then the same spec elsewhere.

Runs DFTB+ when it is configured (see ``common_01_executables.py``);
otherwise it stops with what to set.

The modules of DFTB+ are ``PERIODIC = BOTH``, so the specification of
``dftbplus_01_periodic.py`` works on a molecule too, without ``KPOINTS``. The
``final_geometry`` handler is declared for the optimisation modules only: asking
for it after a single point raises, which is what ``modules=`` is for.

The directory of the Slater-Koster files is never in the spec: AMAC writes
``Prefix`` from ``BASIS`` in the ``env`` of DFTB+ in ``config-amac.json``.
Here it names a ``3ob-3-1/`` directory.
"""

import logging
import sys
from pathlib import Path

import numpy as np
from ase.build import molecule

import amac
from amac import AMAC
from amac.assets import dftbplus

CONFIG_OPTION = "--config="  # configuration file handed to AMAC
PROJECT_CONFIG = Path(__file__).resolve().parents[1] / "config-amac.json"
DEFAULT_RUNS = Path.home() / "amac-runs"
RUNS_NAME = "dftbplus-molecule"


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


OPTIMISATION = {
    "software": "DFTB+",
    "method": "TIGHT_BINDING",
    "method_args": {
        "variant": "DFTB3",
        "SCCTolerance": 1e-7,
        "ThirdOrderFull": True,
        "MaxAngularMomentum": {"C": "p", "O": "p", "H": "s"},
        # Third order needs the Hubbard derivatives of the parameter set.
        "HubbardDerivs": {"C": -0.1492, "O": -0.1575, "H": -0.1857},
    },
    "module": "OPT",
    "parameters": {
        "SLATER_KOSTER_FILES": {
            "variant": "Type2FileNames",
            "Separator": "-",
            "Suffix": ".skf",
        },
        # H-bond correction, expected by the 3ob set: a parameter, not a method
        # argument, since DFTB+ writes it as its own block.
        "HCORRECTION": {"Damping": {"Exponent": 4.0}},
        "OPTIONS": {"WriteResultsTag": True},
        "ANALYSIS": {"MullikenAnalysis": True, "Printforces": True},
    },
}

SPECS = (OPTIMISATION,)


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
    """Optimise formaldehyde and read the geometry back as an ase.Atoms."""
    require("DFTB+")
    root = workdir()
    show_workdir(root)
    calc = AMAC(
        **OPTIMISATION,
        cpu=4,
        workdir=root,
        label="formaldehyde",
        overwrite=True,  # so that the example can be run again
        raise_on_error=False,  # a failed run is reported, not raised
    )
    calc.handler_properties(
        dftbplus.energy, dftbplus.forces, dftbplus.charges, dftbplus.final_geometry
    )
    result = calc.execute(molecule("H2CO"))
    if not result.success:
        # collect() never ran, so the log is read from the run directory itself.
        log = result.context.directory.joinpath("dftb.out")
        tail = log.read_text(encoding="utf-8")[-600:] if log.is_file() else ""
        raise SystemExit(f"DFTB+ failed: {result.errors}\n{tail}")

    optimised = result.properties["final_geometry"]
    forces = np.asarray(result.properties["forces"])
    print(f"Energy: {result.properties['energy']:.6f} eV")
    print(f"Residual |F|: {np.abs(forces).max():.2e} eV/A")
    print(f"C=O: {optimised.get_distance(0, 1):.4f} A")
    print(f"files kept in {calc.directories[0]}")

    # The optimised geometry feeds the next calculation, with any software: it is
    # an ase.Atoms like any other (see demonnano_02_optimisation.py).
    print(optimised.get_chemical_formula(), optimised.get_positions().shape)


if __name__ == "__main__":
    main()
