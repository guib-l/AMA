"""deMon-Nano in process: no input file written by AMAC, native objects kept.

Runs deMon-Nano when it is configured (see ``common_01_executables.py``);
otherwise it stops with what to set. It also needs the ``deMonPy`` library
(``DeMonNanoPy``, installed from its repository).

deMon-Nano is an ``INPROCESS`` software: the library builds the calculation from
the intermediate tree of the specification instead of an input file AMAC would
write. The run directory is still created, the objects of the library stay in
``ctx.objects``, and what the library prints to Python's ``sys.stdout`` lands in
``result.context.stdout``. The library starts ``deMon.x`` itself, so a run still
needs an executable from an explicit source: AMAC resolves it and hands the path
over (see ``common_01_executables.py``). The directory of the Slater-Koster
files is never in the spec: AMAC hands it to the library as ``SKFILE`` from
``BASIS`` in the ``env`` of deMonNano in ``config-amac.json``.
"""

import logging
import sys
from pathlib import Path

from ase.build import molecule

import amac
from amac import AMAC
from amac.assets import demonnano

CONFIG_OPTION = "--config="  # configuration file handed to AMAC
PROJECT_CONFIG = Path(__file__).resolve().parents[1] / "config-amac.json"
DEFAULT_RUNS = Path.home() / "amac-runs"
RUNS_NAME = "demonnano"


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


CALCULATION = {
    "software": "deMonNano",
    "method": "DFTB",  # alias TIGHT_BINDING, as in the catalog
    "method_args": {"variant": "DFTB2"},
    "module": "SINGLE_POINT",
    "parameters": {
        # The library reads a parameter set by name; its directory is BASIS.
        "SLATER_KOSTER_FILES": {"PTYPE": "BIO"},
        "CHARGE": 0,
        "MULTIPLICITY": 1,
        # AMAC adds nothing on its own: the gradient needs this directive.
        "OUTPUT_CONTROL": {"GRAD": True, "MOE": True},
    },
}

SPECS = (CALCULATION,)


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
    """Run a single point in this process and look at what the library left."""
    require("deMonNano")
    root = workdir()
    show_workdir(root)
    calc = AMAC(
        **CALCULATION,
        cpu=4,
        # The executable comes from the configuration file or $DEMON_EXECUTABLE.
        workdir=root,
        label="water",
        keep_files=True,
        overwrite=True,  # so that the example can be run again
    )
    calc.handler_properties(
        demonnano.energy,
        demonnano.forces,
        demonnano.charges,
        ("n_atoms", lambda ctx: len(ctx.atoms)),  # any callable is a handler
    )
    result = calc.execute(molecule("H2O"))
    if not result.success:
        raise SystemExit(f"deMon-Nano failed: {result.errors}")

    print(f"Energy: {result.properties['energy']:.6f} eV")
    print(f"Charges: {result.properties['charges']} e")
    # A handler returns None when the program wrote nothing for it; here the
    # gradient is asked for with GRAD but deMon.out carries no gradient block.
    forces = result.properties["forces"]
    shape = "not written by the program" if forces is None else f"{forces.shape} in eV/A"
    print(f"Forces: {shape}")

    context = result.context
    print(f"objects: {sorted(context.objects)}")  # 'demonnano', 'demonnano.module'
    print(f"calculator: {type(context.objects['demonnano']).__name__}")
    # The library received this path; an in-process run fills no
    # metadata['executable'], which only a file-based run does.
    print(f"executable: {calc.software.resolve_executable(calc.exec_spec)}")
    print(f"files read by the handlers: {sorted(context.files)}")
    print((context.stdout or "")[-500:])  # captured library log


if __name__ == "__main__":
    main()
