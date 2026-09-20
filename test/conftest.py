"""Shared fixtures of the AMAC tests.

The generic chain (``prepare`` -> ``run`` -> ``collect`` -> handlers) is exercised
through the real DFTB+ asset driven by a **stub program**: a small Python script
written in ``tmp_path`` and given to AMAC as an explicit absolute ``executable=``.
It reads the ``dftb_in.hsd`` the composer wrote and writes the output files the
parser reads, so the tests need no DFTB+ installation and nothing is ever looked
up in ``PATH``.

The numbers it writes are deterministic patterns, not physics (:data:`STUB_ENERGY`,
:func:`stub_forces`, :func:`stub_charges`): tests assert on them exactly.
"""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path
from typing import Any

import pytest
from ase import Atoms
from ase.build import molecule

import amac
from amac import AMAC
from amac.config import clear_config_cache
from amac.engine import registry
from amac.engine.registry import get_software
from amac.engine.software import FileIOSoftware

# Configuration file used by the tests marked "real": --amac-config, else the one
# of the repository. Nothing else is ever read: AMAC reads no environment variable.
CONFIG_OPTION = "--amac-config"
PROJECT_CONFIG = Path(__file__).resolve().parents[1] / "config-amac.json"

# Values written by the stub program, in the units of DFTB+ (Hartree, Bohr).
STUB_ENERGY = -4.5
STUB_BAND_ENERGY = -2.5
STUB_FERMI_LEVEL = -0.2
STUB_DIPOLE = (0.0, 0.0, 0.5)
# Output files it may write; "geo_end.gen" only makes sense after an optimisation.
STUB_FILES = ("detailed.out", "results.tag")
# Offset applied to every coordinate of "geo_end.gen", in Angstrom.
STUB_DISPLACEMENT = 0.01

_SKF_FILES = ("O-O.skf", "O-H.skf", "H-O.skf", "H-H.skf", "Si-Si.skf")
_SETTINGS_TOKEN = "@SETTINGS@"
_PYTHON_TOKEN = "@PYTHON@"


def stub_forces(count: int) -> list[list[float]]:
    """Return the forces the stub writes for ``count`` atoms, in Hartree/Bohr.

    Row ``i`` is ``(i + 1) * (0.01, 0.02, 0.03)``, shifted so that the sum over the
    atoms is zero, as a translation-invariant calculation gives.
    """
    rows = [[(index + 1) * step for step in (0.01, 0.02, 0.03)] for index in range(count)]
    means = [sum(row[axis] for row in rows) / count for axis in range(3)]
    return [[row[axis] - means[axis] for axis in range(3)] for row in rows]


def stub_charges(count: int) -> list[float]:
    """Return the net atomic charges the stub writes, in elementary charges.

    Evenly spaced from -0.6 to +0.6, so that the system stays neutral.
    """
    if count == 1:
        return [0.0]
    return [-0.6 + 1.2 * index / (count - 1) for index in range(count)]


# Source of the stub program. The two tokens are replaced by the factory below;
# the script itself only uses the standard library.
_STUB_SOURCE = '''#!@PYTHON@
"""Stub of the dftb+ executable, written by the AMAC test suite."""

import json
import re
import sys
import time
from pathlib import Path

SETTINGS = json.loads(r"""@SETTINGS@""")
INPUT_FILE = Path("dftb_in.hsd")
HARTREE_IN_EV = 27.211386245988


def read_input():
    """Return the atom count and the Slater-Koster Prefix of the input of the run."""
    if not INPUT_FILE.is_file():
        sys.stderr.write("stub dftb+: no dftb_in.hsd in %s\\n" % Path.cwd())
        raise SystemExit(2)
    text = INPUT_FILE.read_text(encoding="utf-8")
    header = re.search(r"GenFormat \\{\\s*\\n\\s*(\\d+)\\s+([CSF])", text)
    if header is None:
        sys.stderr.write("stub dftb+: no geometry in dftb_in.hsd\\n")
        raise SystemExit(3)
    prefix = re.search(r"Prefix\\s*=\\s*(\\S+)", text)
    return int(header.group(1)), (prefix.group(1) if prefix else "")


def forces(count):
    rows = [[(i + 1) * step for step in (0.01, 0.02, 0.03)] for i in range(count)]
    means = [sum(row[axis] for row in rows) / count for axis in range(3)]
    return [[row[axis] - means[axis] for axis in range(3)] for row in rows]


def charges(count):
    if count == 1:
        return [0.0]
    return [-0.6 + 1.2 * i / (count - 1) for i in range(count)]


def detailed_out(count):
    energy = SETTINGS["energy"]
    lines = [
        " Total energy:%26.10f H %15.4f eV" % (energy, energy * HARTREE_IN_EV),
        " Band energy:%27.10f H" % SETTINGS["band_energy"],
        " Fermi level:%27.10f H" % SETTINGS["fermi_level"],
        " SCC converged" if SETTINGS["converged"] else " SCC is NOT converged",
        "",
        " Total Forces",
    ]
    for index, row in enumerate(forces(count), start=1):
        lines.append("%5d%22.12f%22.12f%22.12f" % (index, row[0], row[1], row[2]))
    lines += ["", " Net atomic charges (e)", " Atom         Netcharge"]
    for index, value in enumerate(charges(count), start=1):
        lines.append("%5d%18.8f" % (index, value))
    dipole = " ".join("%.8f" % value for value in SETTINGS["dipole"])
    lines += ["", " Dipole moment:    %s au" % dipole, ""]
    return "\\n".join(lines)


def results_tag(count):
    lines = ["total_energy         :real:0:", " %.12E" % SETTINGS["energy"]]
    lines.append("forces               :real:2:3,%d" % count)
    for row in forces(count):
        lines.append("".join("%22.12E" % value for value in row))
    lines.append("gross_atomic_charges :real:1:%d" % count)
    lines.append("".join("%22.12E" % value for value in charges(count)))
    lines.append("fermi_level          :real:0:")
    lines.append(" %.12E" % SETTINGS["fermi_level"])
    return "\\n".join(lines) + "\\n"


def geo_end_gen(count):
    """Return the geometry of the input with every coordinate moved by a fixed step."""
    text = INPUT_FILE.read_text(encoding="utf-8")
    block = text.split("GenFormat {", 1)[1].split("}", 1)[0]
    rows = [" ".join(line.split()) for line in block.strip().splitlines()]
    step = SETTINGS["displacement"]
    moved = []
    for line in rows[2:]:
        words = line.split()
        coordinates = tuple(float(word) + step for word in words[2:5])
        moved.append("%s %s %.12f %.12f %.12f" % ((words[0], words[1]) + coordinates))
    return "\\n".join([rows[0], rows[1]] + moved) + "\\n"


def main():
    count, prefix = read_input()
    if SETTINGS["delay"] and SETTINGS["delay_atoms"] in (None, count):
        time.sleep(SETTINGS["delay"])
    if count == SETTINGS["fail_atoms"]:
        sys.stderr.write("stub dftb+: refusing a geometry of %d atoms\\n" % count)
        raise SystemExit(SETTINGS["return_code"] or 3)
    writers = {
        "detailed.out": detailed_out,
        "results.tag": results_tag,
        "geo_end.gen": geo_end_gen,
    }
    for name in SETTINGS["files"]:
        Path(name).write_text(writers[name](count), encoding="utf-8")
    print("stub dftb+: %d atoms, Prefix %s" % (count, prefix or "unset"))
    print("stub dftb+: wrote %s" % ", ".join(SETTINGS["files"]))
    if SETTINGS["stderr"]:
        sys.stderr.write(SETTINGS["stderr"])
    raise SystemExit(SETTINGS["return_code"])


main()
'''


def pytest_addoption(parser):
    """Add ``--amac-config``, the configuration file of the tests marked ``real``."""
    parser.addoption(
        CONFIG_OPTION,
        action="store",
        default=None,
        metavar="PATH",
        help=(
            "configuration file given to the tests marked 'real'; defaults to the "
            "config-amac.json of the repository"
        ),
    )


@pytest.fixture(autouse=True)
def isolated_config():
    """Start every test without any configuration file, and leave none behind."""
    amac.reset_configuration()
    yield
    amac.reset_configuration()


@pytest.fixture
def dftbp_stub(tmp_path):
    """Return a factory writing a stub ``dftb+`` and giving back its absolute path.

    Every call writes a new program in its own directory::

        path = dftbp_stub()                # a run that succeeds
        path = dftbp_stub(return_code=1)   # a run that fails
        path = dftbp_stub(files=())        # a run that writes no output
        path = dftbp_stub(delay=5)         # a run to time out
        path = dftbp_stub(fail_atoms=1)    # a run failing on a one-atom image only

    ``fail_atoms`` and ``delay_atoms`` restrict the failure and the delay to the
    images of that atom count, so that a sequence of images can fail in the middle.
    """
    counter = 0

    def make(
        *,
        energy: float = STUB_ENERGY,
        band_energy: float = STUB_BAND_ENERGY,
        fermi_level: float = STUB_FERMI_LEVEL,
        dipole: tuple[float, float, float] = STUB_DIPOLE,
        converged: bool = True,
        files: tuple[str, ...] = STUB_FILES,
        displacement: float = STUB_DISPLACEMENT,
        return_code: int = 0,
        stderr: str = "",
        delay: float = 0.0,
        delay_atoms: int | None = None,
        fail_atoms: int | None = None,
        name: str = "dftb+",
    ) -> Path:
        nonlocal counter
        counter += 1
        settings = {
            "energy": energy,
            "band_energy": band_energy,
            "fermi_level": fermi_level,
            "dipole": list(dipole),
            "converged": converged,
            "files": list(files),
            "displacement": displacement,
            "return_code": return_code,
            "stderr": stderr,
            "delay": delay,
            "delay_atoms": delay_atoms,
            "fail_atoms": fail_atoms,
        }
        directory = tmp_path / f"stub-{counter:02d}"
        directory.mkdir()
        path = directory / name
        source = _STUB_SOURCE.replace(_PYTHON_TOKEN, sys.executable)
        path.write_text(
            source.replace(_SETTINGS_TOKEN, json.dumps(settings)), encoding="utf-8"
        )
        path.chmod(path.stat().st_mode | stat.S_IXUSR)
        return path

    return make


@pytest.fixture
def dftbp_basis(tmp_path) -> Path:
    """Return a directory of Slater-Koster files, as ``BASIS`` designates one."""
    directory = tmp_path / "mio-1-1"
    directory.mkdir()
    for name in _SKF_FILES:
        (directory / name).write_text("stub Slater-Koster file\n", encoding="utf-8")
    return directory


@pytest.fixture
def write_config(tmp_path, isolated_config):
    """Return a factory writing ``config-amac.json`` and giving it to AMAC.

    ``write_config({"DFTB+": {"env": {"BASIS": "..."}}})`` writes the ``software``
    object of the file, hands it to ``amac.set_config`` and returns its path.
    Other top-level keys, such as ``workdir``, are given as keyword arguments.
    """

    def make(software: dict[str, Any], **top_level: Any) -> Path:
        path = tmp_path / "config-amac.json"
        content = {"software": software, **top_level}
        path.write_text(json.dumps(content), encoding="utf-8")
        clear_config_cache()
        amac.set_config(path)
        return path

    return make


@pytest.fixture
def dftbp_configured(write_config, dftbp_basis) -> Path:
    """Give DFTB+ its ``BASIS`` through the configuration file, as a machine does."""
    write_config({"DFTB+": {"env": {"BASIS": str(dftbp_basis)}}})
    return dftbp_basis


@pytest.fixture
def stub_spec() -> dict[str, Any]:
    """Return a valid DFTB+ calculation: SCC-DFTB single point of a molecule."""
    return {
        "software": "DFTB+",
        "method": "TIGHT_BINDING",
        "method_args": {
            "variant": "DFTB2",
            "MaxAngularMomentum": {"O": "p", "H": "s"},
        },
        "module": "SINGLE_POINT",
        "parameters": {
            "SLATER_KOSTER_FILES": {"variant": "Type2FileNames"},
            "ANALYSIS": {"MullikenAnalysis": True, "Printforces": True},
            "OPTIONS": {"WriteResultsTag": True},
        },
    }


@pytest.fixture
def stub_calc(dftbp_stub, dftbp_configured, stub_spec, tmp_path):
    """Return a factory giving an :class:`AMAC` wired to a stub ``dftb+``.

    Keyword arguments go to :class:`AMAC` (calculation or execution ones), and the
    settings of the stub program go in ``stub``::

        calc = stub_calc()                                   # ready to execute()
        calc = stub_calc(stub={"return_code": 1}, raise_on_error=False)
        calc = stub_calc(module="GEOMETRY_OPTIMISATION")
    """

    def make(*, stub: dict[str, Any] | None = None, **kwargs: Any) -> AMAC:
        settings = {
            **stub_spec,
            "workdir": tmp_path / "runs",
            "label": "stub",
            "executable": str(dftbp_stub(**(stub or {}))),
            **kwargs,
        }
        return AMAC(**settings)

    return make


@pytest.fixture
def water() -> Atoms:
    """Return a water molecule, the geometry of most tests."""
    return molecule("H2O")


@pytest.fixture
def no_doc_software(monkeypatch):
    """Register a software without ``doc.json``, which cannot be validated.

    It is registered in a copy of the global registry, so it disappears with the
    test. It writes no input and produces no file: only the behaviour of AMAC in
    front of a software it cannot validate is at stake.
    """
    monkeypatch.setattr(registry, "_REGISTRY", dict(registry._REGISTRY))

    class NoDocSoftware(FileIOSoftware):
        NAME = "NO_DOC_TEST"
        REQUIRES_EXECUTABLE = False

        def prepare(self, ctx):
            """Write no input file."""

        def collect(self, ctx):
            """Produce no file."""

        def command(self, ctx):
            return [sys.executable, "-c", "pass"]

    return registry.register_software(NoDocSoftware)


@pytest.fixture
def real_config(request) -> Path:
    """Give AMAC the configuration file of this machine, or skip the test.

    Tests using it run the real programs, so they only run when a configuration
    file gives them: ``pytest --amac-config=PATH``, else the ``config-amac.json``
    of the repository. Nothing is ever discovered: what the file does not give,
    the test skips.
    """
    given = request.config.getoption("amac_config")
    path = Path(given).expanduser() if given else PROJECT_CONFIG
    if not path.is_file():
        pytest.skip(f"no configuration file {path}: run pytest {CONFIG_OPTION}=PATH")
    amac.set_config(path)
    return path


@pytest.fixture
def real_software(real_config):
    """Return a factory checking that a software is usable, or skipping the test."""

    def require(name: str) -> str:
        location = amac.which(name)
        if location is None or not Path(location.path).is_file():
            pytest.skip(f"{name} has no usable executable in {real_config}")
        if not get_software(name)().configured_env().get("BASIS"):
            pytest.skip(f"{name} has no BASIS in {real_config}")
        try:
            get_software(name)().check_environment()
        except Exception as error:  # noqa: BLE001 - any missing library skips
            pytest.skip(f"{name}: {error}")
        return location.path

    return require
