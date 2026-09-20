"""Where AMAC takes the executable of a software, and what it refuses.

Runnable everywhere: nothing is executed here, only located.

Resolution order, first source set wins (``Software.locate_executable``):

1. ``executable=`` given to ``AMAC(...)`` or to ``execute()``, and
   ``amac.configure(software=..., executable=...)`` for the facade;
2. ``executable`` of ``software.<NAME>`` in the configuration file.

AMAC reads no environment variable. The configuration file is given explicitly,
to one calculator with ``AMAC(config=...)`` or to the process with
``amac.set_config(path)``; without either there is no configuration at all. Its
format::

    {
        "workdir": "~/amac-runs",
        "software": {
            "DFTB+": {
                "executable": "/opt/dftbplus/bin/dftb+",
                "env": {"BASIS": "/data/slako/mio-1-1/"}
            }
        }
    }

AMAC never searches ``PATH``: the value must be an absolute path to an executable
file. It is located once per ``execute()`` call, before any run directory is
created, so a wrong executable leaves nothing behind.

``workdir`` is the default root of the run directories, used when no ``workdir=``
is given. The same file carries ``env``, which the runs of that software receive.
For DFTB+ and deMon-Nano it holds ``BASIS``, the directory of the Slater-Koster
files, and that variable is its only source: giving it in the specification is
refused.
"""

import json
import sys
import tempfile
from pathlib import Path

from ase.build import molecule

import amac
from amac import AMAC
from amac.engine.registry import available_software, get_software

CONFIG_OPTION = "--config="  # configuration file handed to AMAC
PROJECT_CONFIG = Path(__file__).resolve().parents[1] / "config-amac.json"

# A single point used below to show what execute() refuses before running anything.
SINGLE_POINT = {
    "software": "DFTB+",
    "method": "TIGHT_BINDING",
    "method_args": {"variant": "DFTB2", "MaxAngularMomentum": {"O": "p", "H": "s"}},
    "module": "SINGLE_POINT",
    "parameters": {"SLATER_KOSTER_FILES": {"variant": "Type2FileNames"}},
}

SPECS = (SINGLE_POINT,)


def config_file() -> Path:
    """Return the configuration file of this run.

    ``--config=PATH`` wins, else the ``config-amac.json`` of this repository.
    AMAC reads no environment variable: the file is handed to it explicitly.
    """
    for argument in sys.argv[1:]:
        if argument.startswith(CONFIG_OPTION):
            return Path(argument.removeprefix(CONFIG_OPTION)).expanduser()
    return PROJECT_CONFIG


def show_sources() -> None:
    """Print the executable AMAC would use for each software, and where from."""
    config = config_file()
    print(f"Configuration file: {config} (exists: {config.is_file()})")
    if not config.is_file():
        print(f"Nothing is guessed: write one and pass {CONFIG_OPTION}{config}")
        return
    amac.set_config(config)
    for name in available_software():
        location = amac.which(name)
        if location is None:
            print(f"{name:8s} no executable; give one in {config}")
        else:
            print(f"{name:8s} {location.path} (from {location.source})")


def show_a_written_configuration() -> None:
    """Write a configuration file, hand it to AMAC, then forget it."""
    content = {"software": {"DFTB+": {"executable": "/opt/dftbplus/bin/dftb+"}}}
    with tempfile.TemporaryDirectory(prefix="amac-config-") as directory:
        path = Path(directory) / "config-amac.json"
        path.write_text(json.dumps(content), encoding="utf-8")
        # For the whole process: every calculator without its own config= reads it.
        amac.set_config(path)
        print(f"With set_config: {amac.which('DFTB+')}")
        # For one call only: which() and AMAC() take the file they are given.
        print(f"With config=: {amac.which('DFTB+', config=path)}")
    amac.set_config(None)
    print(f"Without any configuration: {amac.which('DFTB+')}")


def show_refusals() -> None:
    """Two values AMAC refuses, both before creating a run directory."""
    calc = AMAC(**SINGLE_POINT, label="never-runs")
    water = molecule("H2O")
    for executable in ("dftb+", "/opt/missing/dftb+"):
        try:
            calc.execute(water, executable=executable)
        except amac.ExecutableNotFoundError as error:
            print(f"Refused: {error}")


def show_configured_env() -> None:
    """Show the ``env`` each software receives from the configuration file."""
    config = config_file()
    for name in available_software():
        env = get_software(name)(config if config.is_file() else None).configured_env()
        basis = env.get("BASIS", "unset: runs would be refused")
        print(f"{name:8s} env={sorted(env)} BASIS={basis}")


def main() -> None:
    """Show the two sources, what AMAC refuses, and the configured env."""
    show_sources()
    show_a_written_configuration()
    show_refusals()
    show_configured_env()
    amac.set_config(None)


if __name__ == "__main__":
    main()
