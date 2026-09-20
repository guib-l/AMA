"""Handlers: custom ones, required files, failures, module compatibility.

Runs DFTB+ when it is configured (see ``common_01_executables.py``); otherwise it
stops with what to set.

A handler is any callable receiving the run context. A failing handler, or one
whose ``requires_files`` match no produced file, has no entry in
``result.properties``: with ``handler_errors="collect"`` (the default) its
``HandlerError`` goes to ``result.errors``, with ``"raise"`` the first one stops
``execute()``. ``result.success`` only reflects the run itself.
"""

import logging
import re
import sys
from pathlib import Path

from ase.build import molecule

import amac
from amac import AMAC
from amac.assets import dftbplus
from amac.engine.handlers import handler

CONFIG_OPTION = "--config="  # configuration file handed to AMAC
PROJECT_CONFIG = Path(__file__).resolve().parents[1] / "config-amac.json"
DEFAULT_RUNS = Path.home() / "amac-runs"
RUNS_NAME = "handlers"


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


LOG_FILE = "dftb.out"  # where AMAC redirects the standard output of DFTB+

CALCULATION = {
    "software": "DFTB+",
    "method": "TIGHT_BINDING",
    "method_args": {"variant": "DFTB2", "MaxAngularMomentum": {"O": "p", "H": "s"}},
    "module": "SINGLE_POINT",
    "parameters": {
        "SLATER_KOSTER_FILES": {"variant": "Type2FileNames"},
        "ANALYSIS": {"MullikenAnalysis": True, "Printforces": True},
        "OPTIONS": {"WriteResultsTag": True},
    },
}

SPECS = (CALCULATION,)


@handler(requires_files=("hessian.out",))  # only a Hessian run writes it
def hessian_matrix(ctx) -> str:
    """Never runs here: its required file is not produced by a single point."""
    return ctx.files["hessian.out"].read_text(encoding="utf-8")


@handler(requires_files=(LOG_FILE,))  # no software: accepted by all of them
def scc_cycles(ctx) -> int | None:
    """Return the number of SCC iterations read in the log of the run."""
    text = ctx.files[LOG_FILE].read_text(encoding="utf-8")
    steps = re.findall(r"^\s*(\d+)\s+-?\d+\.\d+E?[-+]?\d*", text, flags=re.MULTILINE)
    return int(steps[-1]) if steps else None


def log_size(ctx) -> int:
    """Return the size of the log; plain callable, without metadata."""
    return ctx.files[LOG_FILE].stat().st_size


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
    """Collect handler failures, then raise the first one."""
    require("DFTB+")
    root = workdir()
    show_workdir(root)
    water = molecule("H2O")

    # collect: failures are recorded, the other properties are still computed.
    calc = AMAC(**CALCULATION, workdir=root, label="collect", overwrite=True)
    calc.handler_properties(
        dftbplus.energy,  # requires_files=("detailed.out",)
        dftbplus.orbital_energies,  # runs, but returns None: nothing wrote them
        hessian_matrix,  # skipped: hessian.out is missing from this run
        scc_cycles,
        log_size,
        ("broken", lambda ctx: ctx.objects["not-there"]),  # KeyError
    )
    result = calc.execute(water)
    print(result.success, sorted(result.properties), calc.directories)
    for error in result.errors:
        print(f"  {error.handler}: {error} (missing: {error.missing_files})")

    # modules=: final_geometry only makes sense after a geometry optimisation.
    try:
        calc.handler_properties(dftbplus.energy, dftbplus.final_geometry)
    except ValueError as error:
        print(error)
    # skip_incompatible keeps the compatible ones, with a single warning.
    calc.handler_properties(
        dftbplus.energy, dftbplus.final_geometry, skip_incompatible=True
    )
    print([meta.name for meta in calc.handlers])

    # raise: the first failure stops execute(), with the original exception chained.
    strict = AMAC(
        **CALCULATION,
        workdir=root,
        label="raise",
        handler_errors="raise",
        overwrite=True,
    )
    strict.handler_properties(dftbplus.energy, ("broken", lambda ctx: 1 / 0))
    try:
        strict.execute(water)
    except amac.HandlerError as error:
        print(f"{error} <- {error.__cause__!r}")


if __name__ == "__main__":
    main()
