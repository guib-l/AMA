"""The same DFTB2 single point with DFTB+ and with deMon-Nano.

Runs both programs when they are configured (see ``common_01_executables.py``);
otherwise it stops with what to set. deMon-Nano also needs its ``deMonPy`` library.

What AMAC makes common is the canonical part of the description: the method
(``TIGHT_BINDING``, the name the catalog gives the DFTB family), its variant
(``DFTB2``) and the module. What stays per software is what the programs really
ask for: each one declares its Slater-Koster files its own way, and deMon-Nano
needs ``OUTPUT_CONTROL`` to print the gradient. Handlers belong to a software too,
but their names and their units (eV, eV/A) are the same.

The directory of the Slater-Koster files is never in the spec: it is ``BASIS``
in the ``env`` of each software in ``config-amac.json``, written as ``Prefix`` for
DFTB+ and handed as ``SKFILE`` to deMon-Nano.
"""

import logging
import sys
from pathlib import Path

from ase.build import molecule

import amac
from amac import AMAC
from amac.assets import demonnano, dftbplus

CONFIG_OPTION = "--config="  # configuration file handed to AMAC
PROJECT_CONFIG = Path(__file__).resolve().parents[1] / "config-amac.json"
DEFAULT_RUNS = Path.home() / "amac-runs"
RUNS_NAME = "dftb2-comparison"


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


# Canonical part, identical for both programs.
LEVEL_OF_THEORY = {
    "method": "TIGHT_BINDING",
    "method_args": {"variant": "DFTB2"},
    "module": "SINGLE_POINT",
}

DFTBPLUS = {
    "software": "DFTB+",
    **LEVEL_OF_THEORY,
    # DFTB2 implies SCC = Yes: the variant sets it, it is not written here.
    "method_args": {
        "variant": "DFTB2",
        "SCCTolerance": 1e-6,
        "MaxAngularMomentum": {"O": "p", "H": "s"},
    },
    "parameters": {
        "SLATER_KOSTER_FILES": {
            "variant": "Type2FileNames",
            "Separator": "-",
            "Suffix": ".skf",
        },
        "ANALYSIS": {"MullikenAnalysis": True, "Printforces": True},
        "OPTIONS": {"WriteResultsTag": True},
    },
}

DEMONNANO = {
    "software": "deMonNano",
    **LEVEL_OF_THEORY,
    "parameters": {
        # The library reads its parameter set by name, not file by file.
        "SLATER_KOSTER_FILES": {"PTYPE": "BIO"},
        "CHARGE": 0,
        "MULTIPLICITY": 1,
        # AMAC adds nothing on its own: forces need this directive.
        "OUTPUT_CONTROL": {"GRAD": True},
    },
}

SPECS = (DFTBPLUS, DEMONNANO)

HANDLERS = {
    "DFTB+": (dftbplus.energy, dftbplus.forces, dftbplus.charges),
    "deMonNano": (demonnano.energy, demonnano.forces, demonnano.charges),
}


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
    """Run the same level of theory with both programs and compare."""
    root = workdir()
    show_workdir(root)
    for spec in SPECS:
        require(spec["software"])
    water = molecule("H2O")
    energies = {}
    for spec in SPECS:
        software = spec["software"]
        calc = AMAC(
            **spec,
            workdir=root,
            label=f"water-{software.lower()}",
            overwrite=True,  # so that the example can be run again
            raise_on_error=False,  # a failed run is reported, not raised
        )
        calc.handler_properties(*HANDLERS[software])
        result = calc.execute(water)
        if not result.success:
            raise SystemExit(f"{software} failed: {result.errors}")
        print(f"  {software} ran in {result.context.directory}")
        energies[software] = result.properties["energy"]
        charge = result.properties["charges"][0]
        print(f"{software:10s} E = {energies[software]:12.6f} eV  q(O) = {charge:+.4f}")

    # Both handlers return eV: the difference is the one between the programs,
    # not between their unit conventions.
    difference = energies["DFTB+"] - energies["deMonNano"]
    print(f"DFTB+ - deMonNano = {difference:+.6f} eV")


if __name__ == "__main__":
    main()
