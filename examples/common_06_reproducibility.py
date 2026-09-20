"""Save a calculation as JSON on a cluster node and run it again elsewhere.

Runs DFTB+ when it is configured (see ``common_01_executables.py``); otherwise it
stops with what to set.

``to_dict()`` keeps the specification, the execution settings (``env`` values
masked), the software, the validation mode, the requested driver and the
importable handlers. ``AMAC.from_dict`` imports these handlers again: only load
files you trust. Everything that depends on the machine (``workdir``,
``executable``, ``cpu``, ``ram``, ``env``, ...) is overridden for one call in
``execute()``.
"""

import json
import logging
import sys
from pathlib import Path

from ase.build import molecule

import amac
from amac import AMAC
from amac.assets import dftbplus

CONFIG_OPTION = "--config="  # configuration file handed to AMAC
PROJECT_CONFIG = Path(__file__).resolve().parents[1] / "config-amac.json"
DEFAULT_RUNS = Path.home() / "amac-runs"
RUNS_NAME = "reproducibility"


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


SPEC_NAME = "formaldehyde-opt.amac.json"

CALCULATION = {
    "software": "DFTB+",
    "method": "TIGHT_BINDING",
    "method_args": {
        "variant": "DFTB2",
        "SCCTolerance": 1e-7,
        "MaxAngularMomentum": {"C": "p", "O": "p", "H": "s"},
    },
    "module": "OPT",  # alias of GEOMETRY_OPTIMISATION
    "parameters": {
        "SLATER_KOSTER_FILES": {"variant": "Type2FileNames"},
        "ANALYSIS": {"MullikenAnalysis": True, "Printforces": True},
        "OPTIONS": {"WriteResultsTag": True},
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


def prepare_on_cluster(spec_file: Path) -> None:
    """Describe a long optimisation with the settings of the cluster, and save it."""
    calc = AMAC(
        **CALCULATION,
        cpu=32,
        ram=64000,  # MB
        timeout=12 * 3600,  # s; beyond that the whole process group is killed
        workdir="/scratch/amac",
        outdir=Path.home() / "results",  # copy of each run directory
        keep_files=False,  # working directory removed after the handlers
        env={"OMP_STACKSIZE": "512M"},
        label="formaldehyde-opt",
        overwrite=True,
    )
    calc.handler_properties(dftbplus.energy, dftbplus.final_geometry)
    # env values are masked by default; handlers are stored as "module:qualname".
    spec_file.parent.mkdir(parents=True, exist_ok=True)
    spec_file.write_text(json.dumps(calc.to_dict(), indent=4), encoding="utf-8")
    print(f"saved {spec_file}")


def run_elsewhere(spec_file: Path, root: Path) -> None:
    """Rebuild the calculation on a workstation and run it with local settings."""
    data = json.loads(spec_file.read_text(encoding="utf-8"))
    calc = AMAC.from_dict(data)  # warns: OMP_STACKSIZE was masked, pass it again
    print([meta.name for meta in calc.handlers])  # ['energy', 'final_geometry']

    result = calc.execute(
        molecule("H2CO"),
        workdir=root,
        outdir=None,
        keep_files=True,
        cpu=2,
        ram=4000,
        timeout=600,
        raise_on_error=False,  # a failed run is reported, not raised
        env={"OMP_STACKSIZE": "64M"},
    )
    if not result.success:
        raise SystemExit(f"DFTB+ failed: {result.errors}")
    path = calc.store(root / "formaldehyde-opt")
    [reloaded] = amac.load(path)
    provenance = reloaded.provenance
    print(f"{provenance['software']} on {provenance['hostname']}")
    print(f"run directory: {provenance['directory']}")
    print(f"cpu={provenance['exec_spec']['cpu']} env={provenance['exec_spec']['env']}")
    print(f"energy={result.properties['energy']:.8f} eV")

    # A forgotten property, read again in the kept files, without running DFTB+:
    # from the calculator when the run directory is at hand...
    charges = calc.reprocess(result.context.directory, handlers=[dftbplus.charges])
    print(f"charges={charges.properties['charges']}")
    # ... or from a stored result, which rebuilds the calculator from its provenance.
    forces = amac.reprocess(reloaded, [dftbplus.forces])
    print(f"max |F|={abs(forces.properties['forces']).max():.2e} eV/A")


def show_workdir(root: Path) -> None:
    """Print where the files go, and let AMAC log each run directory."""
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stdout)
    print(f"workdir: {root}")


def main() -> None:
    """Both steps; on real machines they run on two different hosts."""
    require("DFTB+")
    root = workdir()
    show_workdir(root)
    spec_file = root / SPEC_NAME
    prepare_on_cluster(spec_file)
    run_elsewhere(spec_file, root)


if __name__ == "__main__":
    main()
