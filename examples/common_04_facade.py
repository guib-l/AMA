"""Configure a workstation once, then use the module facade.

Runs the real programs when they are configured (see
``common_01_executables.py``); otherwise it stops with what to set.

``amac.configure`` only affects ``amac.calculator`` and ``amac.run``; an ``AMAC``
built directly ignores it. Priority: global defaults < per-software defaults <
keyword arguments of ``calculator``, ``validate`` included. ``configure`` fills
the explicit source of the executable, so it wins over ``$<NAME>_EXECUTABLE`` and
over the configuration file. The facade state is global to the process and not
thread-safe.
"""

import logging
import sys
from pathlib import Path

from ase.build import molecule

import amac
from amac.assets import demonnano, dftbplus

CONFIG_OPTION = "--config="  # configuration file handed to AMAC
PROJECT_CONFIG = Path(__file__).resolve().parents[1] / "config-amac.json"
DEFAULT_RUNS = Path.home() / "amac-runs"
RUNS_NAME = "facade"


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


# Calculation keys only: what amac.calculator() takes as parameters.
DFTBPLUS_CALCULATION = {
    "method": "TIGHT_BINDING",
    "method_args": {"variant": "DFTB2", "MaxAngularMomentum": {"O": "p", "H": "s"}},
    "module": "SINGLE_POINT",
    "parameters": {
        # Prefix comes from BASIS in the env of DFTB+ in config-amac.json.
        "SLATER_KOSTER_FILES": {"variant": "Type2FileNames"},
        "ANALYSIS": {"MullikenAnalysis": True},
        "OPTIONS": {"WriteResultsTag": True},
    },
}

DEMONNANO_CALCULATION = {
    "method": "TIGHT_BINDING",
    "method_args": {"variant": "DFTB2"},
    "module": "SINGLE_POINT",
    "parameters": {
        "SLATER_KOSTER_FILES": {"PTYPE": "BIO"},
        "CHARGE": 0,
        "MULTIPLICITY": 1,
    },
}

SPECS = (
    {"software": "DFTB+", **DFTBPLUS_CALCULATION},
    {"software": "deMonNano", **DEMONNANO_CALCULATION},
)


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


def configure_workstation(root: Path) -> None:
    """Defaults of this machine: for every software, then per software."""
    amac.configure(
        cpu=4,
        ram=8000,
        workdir=root,
        validate="strict",
        overwrite=True,  # so that the example can be run again
    )
    amac.configure(software="DFTB+", driver="auto", timeout=3600)
    amac.configure(software="deMonNano", cpu=2)
    # which() ignores configure(): it only reads the variable and the file.
    print(f"which(DFTB+) = {amac.which('DFTB+')}")


def show_workdir(root: Path) -> None:
    """Print where the files go, and let AMAC log each run directory."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    print(f"workdir: {root}")


def main() -> None:
    """Create calculators with the facade and run them."""
    require("DFTB+")
    require("deMonNano")
    root = workdir()
    show_workdir(root)
    configure_workstation(root)
    water = molecule("H2O")

    # Current calculator: DFTB+, with the cpu and the driver of configure().
    dftbp = amac.calculator(
        parameters=DFTBPLUS_CALCULATION,
        platform="DFTB+",
        label="water-dftbplus",
        handlers=[dftbplus.energy],
    )
    print(f"DFTB+ driver: {dftbp.driver.name} ({dftbp.driver.fallback})")
    print(amac.run(water).properties)

    # Handlers for this call only; those of the calculator are restored after it.
    detailed = amac.run(
        water,
        handlers=[dftbplus.energy, dftbplus.charges],
        label="water-dftbplus-detailed",
    )
    print(sorted(detailed.properties), [meta.name for meta in dftbp.handlers])

    # deMon-Nano becomes the current calculator; cpu given here wins over
    # configure(), which itself won over the global default.
    amac.calculator(
        parameters=DEMONNANO_CALCULATION,
        platform="deMonNano",
        label="water-demonnano",
        cpu=1,
        handlers=[demonnano.energy, demonnano.charges],
    )
    print(amac.run(water).properties)

    # An explicit calculator can still be used, without becoming the current one.
    print(amac.run(water, calc=dftbp, label="water-dftbplus-again").properties)
    print(f"DFTB+ wrote in {dftbp.workdir}: {[p.name for p in dftbp.directories]}")

    amac.reset_configuration()


if __name__ == "__main__":
    main()
