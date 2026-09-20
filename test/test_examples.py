"""Checks on the scripts of ``examples/``.

Most of them run a real program, so they are not executed here: what is checked is
their content. Every specification they expose in ``SPECS`` must pass the
validation of its software in ``"strict"`` mode, and every one in
``INVALID_SPECS`` must be refused. This is what keeps the examples in step with
the ``doc.json`` files.

Two scripts need no program at all and are run as they are. ``quickstart.py`` is
run too, but only when this machine is configured for DFTB+ (marker ``real``).

The scripts read no environment variable: their configuration file is
``--config=PATH``, and the ``config-amac.json`` of the repository without it.
"""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

from amac import AMAC
from amac.exceptions import ConfigurationError, DriverUnavailableError, ValidationError

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
SCRIPTS = sorted(EXAMPLES.glob("*.py"))
# These need no program and no library: they only locate and read.
RUNNABLE = ("common_01_executables", "common_02_catalog")


def empty_config(directory: Path) -> Path:
    """Write a configuration file giving no software, as a machine without one."""
    path = directory / "config-amac.json"
    path.write_text(json.dumps({"software": {}}), encoding="utf-8")
    return path


def _import(path: Path) -> ModuleType:
    """Import a script without running its ``main()``."""
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_examples_exist():
    """One series per software, plus the software-independent ones."""
    assert len(SCRIPTS) >= 10
    prefixes = {path.stem.split("_")[0] for path in SCRIPTS}
    assert {"common", "dftbplus", "demonnano", "quickstart"} <= prefixes


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda path: path.stem)
def test_specs_validate(path, write_config, tmp_path):
    """Every SPECS entry is accepted, every INVALID_SPECS entry is refused."""
    # BASIS is mandatory for both software and comes from the configuration only.
    basis = str(tmp_path / "basis")
    write_config(
        {"DFTB+": {"env": {"BASIS": basis}}, "DEMON": {"env": {"BASIS": basis}}}
    )
    module = _import(path)
    for kwargs in getattr(module, "SPECS", ()):
        try:
            calc = AMAC(**kwargs, validate="strict")
        except (ConfigurationError, DriverUnavailableError) as error:
            # Missing library or driver: an environment matter, not a wrong spec.
            pytest.skip(f"{kwargs.get('software')}: {error}")
        assert calc.validated
    for kwargs in getattr(module, "INVALID_SPECS", ()):
        with pytest.raises(ValidationError):
            AMAC(**kwargs, validate="strict")


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda path: path.stem)
def test_examples_expose_specs_and_main(path):
    """Every script exposes what the tests and the reader expect."""
    module = _import(path)
    assert getattr(module, "SPECS", None) is not None, "no SPECS"
    assert callable(module.main), "no main()"
    assert module.__doc__, "no module docstring"


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda path: path.stem)
def test_examples_take_their_workdir_from_the_command_line(path, monkeypatch, tmp_path):
    """Every example that writes takes its directory from its first argument."""
    module = _import(path)
    if not hasattr(module, "workdir"):
        pytest.skip(f"{path.stem} writes nothing")

    monkeypatch.setattr(sys, "argv", ["example", str(tmp_path / "from-argv")])
    assert tmp_path / "from-argv" in module.workdir().parents

    # An option is not a directory, and without an argument nothing is guessed.
    monkeypatch.setattr(sys, "argv", ["example", "--config=/somewhere/config.json"])
    assert module.workdir() == Path(module.DEFAULT_RUNS) / module.RUNS_NAME


@pytest.mark.parametrize("path", SCRIPTS, ids=lambda path: path.stem)
def test_examples_take_their_configuration_from_the_command_line(
    path, monkeypatch, tmp_path
):
    """``--config=PATH`` wins over the configuration file of the repository."""
    module = _import(path)
    if not hasattr(module, "config_file"):
        pytest.skip(f"{path.stem} needs no configuration")

    given = empty_config(tmp_path)
    monkeypatch.setattr(sys, "argv", ["example", f"--config={given}"])
    assert module.config_file() == given

    monkeypatch.setattr(sys, "argv", ["example"])
    assert module.config_file() == ROOT / "config-amac.json"


@pytest.mark.parametrize("name", RUNNABLE)
def test_runnable_examples(name, tmp_path):
    """The two scripts needing no program run from the repository root."""
    given = empty_config(tmp_path)
    completed = subprocess.run(
        [sys.executable, "-m", f"examples.{name}", f"--config={given}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_examples_stop_without_an_executable(tmp_path):
    """A script needing a program says what to set instead of failing midway."""
    given = empty_config(tmp_path)
    completed = subprocess.run(
        [sys.executable, str(EXAMPLES / "common_05_handlers.py"), f"--config={given}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode != 0
    assert f"No executable for DFTB+ in {given}" in completed.stderr
    assert "--config=/path/to/config-amac.json" in completed.stderr


def test_examples_stop_without_a_configuration_file(tmp_path):
    """A configuration file that does not exist stops the script, too."""
    missing = tmp_path / "absent.json"
    script = str(EXAMPLES / "common_05_handlers.py")
    completed = subprocess.run(
        [sys.executable, script, f"--config={missing}"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert completed.returncode != 0
    assert f"No configuration file {missing}" in completed.stderr
    assert "examples/common_01_executables.py" in completed.stderr


@pytest.mark.real
def test_quickstart_runs(tmp_path, real_config, real_software):
    """The quickstart really runs DFTB+, when this machine is configured for it."""
    real_software("DFTB+")
    completed = subprocess.run(
        [
            sys.executable,
            str(EXAMPLES / "quickstart.py"),
            str(tmp_path),
            f"--config={real_config}",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert "[AMAC] success=True" in completed.stdout
    assert completed.stdout.count("[facade] image_") == 2
    assert f"[AMAC] workdir={tmp_path}" in completed.stdout
    # The run directory of each image is logged by AMAC itself.
    assert f"DFTBP: run directory {tmp_path / 'water'}" in completed.stdout
    assert (tmp_path / "store-dftb2-water.json").is_file()
    assert (tmp_path / "facade" / "image_001").is_dir()
