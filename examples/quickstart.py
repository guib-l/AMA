"""Quickstart: one SCC-DFTB single point with DFTB+, with the class and the facade.

Usage::

    python examples/quickstart.py [WORKDIR] [--config=PATH]

Everything this script writes goes under ``WORKDIR``: the first argument that is
not an option wins, and without it a temporary directory removed at the end. The
directory in use is printed, and AMAC logs the run directory of each image.

The script runs the real program, so it needs a configuration file giving DFTB+:

- its ``executable``;
- ``BASIS`` in its ``env``, the directory of the Slater-Koster files.

The file is ``--config=PATH``, else the ``config-amac.json`` of this repository;
AMAC reads no environment variable. Both keys are explained in
``common_01_executables.py``. Nothing is guessed: without them the script stops
with a message instead of running anything.
"""

import logging
import sys
import tempfile
from pathlib import Path

import numpy as np
from ase.build import molecule

try:
    import amac
except ModuleNotFoundError:
    # AMAC is not packaged yet: make the root of the repository importable.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import amac

from amac import AMAC
from amac.assets import dftbplus
from amac.engine.registry import get_software

SOFTWARE = "DFTB+"
CONFIG_OPTION = "--config="  # configuration file handed to AMAC
PROJECT_CONFIG = Path(__file__).resolve().parents[1] / "config-amac.json"

# Software-independent description of the calculation: what is computed, and how.
CALCULATION = {
    "method": "TIGHT_BINDING",  # the DFTB family, as the catalog names it
    "method_args": {
        "variant": "DFTB2",  # SCC-DFTB; the variant sets SCC = Yes by itself
        "SCCTolerance": 1e-6,
        "MaxAngularMomentum": {"O": "p", "H": "s"},
    },
    "module": "SINGLE_POINT",
    "parameters": {
        # Prefix is written from BASIS: never give it here.
        "SLATER_KOSTER_FILES": {"variant": "Type2FileNames"},
        "ANALYSIS": {"MullikenAnalysis": True, "Printforces": True},
        "OPTIONS": {"WriteResultsTag": True},
    },
}

SPECS = ({"software": SOFTWARE, **CALCULATION},)


def config_file() -> Path:
    """Return the configuration file of this run.

    ``--config=PATH`` wins, else the ``config-amac.json`` of this repository.
    AMAC reads no environment variable: the file is handed to it explicitly.
    """
    for argument in sys.argv[1:]:
        if argument.startswith(CONFIG_OPTION):
            return Path(argument.removeprefix(CONFIG_OPTION)).expanduser()
    return PROJECT_CONFIG


def require_dftbplus() -> str:
    """Return the configured DFTB+ executable, or stop with the command to run.

    The configuration file of :func:`config_file` is handed to
    ``amac.set_config``; AMAC never searches ``PATH``.
    """
    config = config_file()
    command = f"python {sys.argv[0]} {CONFIG_OPTION}/path/to/config-amac.json"
    if not config.is_file():
        raise SystemExit(
            f"No configuration file {config}.\nWrite one and run:\n  {command}\n"
            "(see examples/common_01_executables.py for its format)."
        )
    amac.set_config(config)
    location = amac.which(SOFTWARE)
    if location is None:
        raise SystemExit(
            f"No executable for {SOFTWARE} in {config}: give it as "
            f'"software" -> "{SOFTWARE}" -> "executable".\n  {command}'
        )
    if not get_software(SOFTWARE)().configured_env().get("BASIS"):
        raise SystemExit(
            f"No BASIS for {SOFTWARE} in {config}: it is the directory of the "
            f"Slater-Koster files, and its only source.\n  {command}"
        )
    return location.path


def show_workdir(root: Path) -> None:
    """Print where the files go, and let AMAC log each run directory."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    print(f"[AMAC] workdir={root}")


def with_the_class(workdir: Path) -> None:
    """Run one geometry with the ``AMAC`` class, then store the result."""
    calc = AMAC(
        software=SOFTWARE,
        **CALCULATION,
        cpu=2,
        workdir=workdir,
        label="water",
    )
    calc.handler_properties(
        dftbplus.energy,
        dftbplus.forces,
        dftbplus.charges,
        ("atom_count", lambda ctx: len(ctx.atoms)),  # any callable is a handler
    )
    result = calc.execute(molecule("H2O"))
    print(f"[AMAC] success={result.success} directory={result.context.directory}")
    if not result.success:
        raise SystemExit(f"DFTB+ failed: {result.errors}")

    forces = np.asarray(result.properties["forces"])
    print(f"[AMAC] energy={result.properties['energy']:.6f} eV")
    print(f"[AMAC] max |F|={np.abs(forces).max():.4e} eV/A")
    print(f"[AMAC] charges={np.round(result.properties['charges'], 4).tolist()} e")

    path = calc.store(workdir / "store-dftb2-water")
    [reloaded] = amac.load(path)
    provenance = reloaded.provenance
    print(f"[AMAC] stored {path}, software={provenance['software']}")
    print(f"[AMAC] duration={provenance['duration']:.3f} s")
    # The same path is on the calculator, in the context and in the provenance.
    assert calc.directories == [result.context.directory]
    assert provenance["directory"] == str(result.context.directory)


def with_the_facade(workdir: Path) -> None:
    """Same calculation through the module facade, on two geometries."""
    amac.configure(cpu=2, workdir=workdir)
    amac.calculator(
        parameters=CALCULATION,
        platform=SOFTWARE,
        label="facade",
        handlers=[dftbplus.energy],
    )
    results = amac.run([molecule("H2O"), molecule("H2O2")])
    for result in results:
        name = result.context.directory.name
        print(f"[facade] {name} energy={result.properties['energy']:.6f} eV")
    amac.reset_configuration()


def main() -> None:
    """Run the same calculation both ways, in the chosen directory."""
    executable = require_dftbplus()
    print(f"[AMAC] using {executable}")
    given = next((arg for arg in sys.argv[1:] if not arg.startswith("-")), None)
    if given:
        workdir = Path(given).expanduser()
        workdir.mkdir(parents=True, exist_ok=True)
        show_workdir(workdir)
        with_the_class(workdir)
        with_the_facade(workdir)
        return
    with tempfile.TemporaryDirectory(prefix="amac-quickstart-") as directory:
        workdir = Path(directory)
        show_workdir(workdir)
        with_the_class(workdir)
        with_the_facade(workdir)


if __name__ == "__main__":
    main()
