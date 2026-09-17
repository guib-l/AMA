"""Reading of the ORCA output files, as pure functions.

Every function takes text and returns plain data, so that the parsers are testable
without ORCA and without a ``RunContext``. :func:`parse_directory` gathers them in
an :class:`OrcaOutput`.

Values keep the units of the program: Hartree for energies, Hartree/Bohr for
gradients, atomic units for the dipole, cm^-1 for the frequencies. The handlers of
``amac.assets.orca.handlers`` convert them to ASE units.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from ase import Atoms
from ase.io import read

OUTPUT_FILE = "orca.out"
ENGRAD_FILE = "orca.engrad"
HESSIAN_FILE = "orca.hess"
GEOMETRY_FILE = "orca.xyz"
TRAJECTORY_FILE = "orca_trj.xyz"

_FINAL_ENERGY = re.compile(r"FINAL SINGLE POINT ENERGY\s+(-?\d+\.\d+)")
_TERMINATION = "ORCA TERMINATED NORMALLY"
# "   0 O :   -0.377875" in the Mulliken and Loewdin charge tables.
_CHARGE_ROW = re.compile(r"^\s*\d+\s+[A-Za-z]{1,3}\s*:\s*(-?\d+\.\d+)")
_DIPOLE = re.compile(r"Total Dipole Moment\s*:\s*(.+)")
# "   0   2.0000     -18.995659      -516.9047" in the ORBITAL ENERGIES table.
_ORBITAL_ROW = re.compile(
    r"^\s*\d+\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s+(-?\d+\.\d+)\s*$"
)
# "   6:      1638.62 cm**-1" in the VIBRATIONAL FREQUENCIES section.
_FREQUENCY_ROW = re.compile(r"^\s*\d+:\s+(-?\d+\.\d+)\s+cm\*\*-1")
# "    0       0.000000" of the $vibrational_frequencies block of orca.hess.
_FREQUENCY_PAIR = re.compile(r"^\s*\d+\s+(-?\d+\.\d+)\s*$")
# "STATE  1:  E=   0.286451 au      7.794 eV" of the excited state modules.
_STATE = re.compile(r"^\s*STATE\s+\d+\s*:\s*E=\s*(-?\d+\.\d+)\s+au", re.MULTILINE)
_CHARGE_TABLES = {"MULLIKEN ATOMIC CHARGES": "mulliken", "LOEWDIN ATOMIC CHARGES": "loewdin"}
_ORBITAL_TABLE = "ORBITAL ENERGIES"
_FREQUENCY_TABLE = "VIBRATIONAL FREQUENCIES"


@dataclass(frozen=True)
class OrcaOutput:
    """Values read in the output files of one ORCA run, in program units.

    Attributes:
        energy: Final single point energy, Hartree.
        forces: Forces, Hartree/Bohr, shape ``(n, 3)``; the opposite of the
            gradient of ``orca.engrad``.
        dipole: Dipole moment, atomic units, shape ``(3,)``.
        charges: Atomic charges in elementary charges, keyed by population
            analysis (``"mulliken"``, ``"loewdin"``), shape ``(n,)`` each.
        orbital_energies: Orbital energies, Hartree, shape ``(m,)``.
        occupations: Occupations of ``orbital_energies``, same shape.
        frequencies: Harmonic frequencies, cm^-1, shape ``(3n,)``.
        hessian: Second derivatives, Hartree/Bohr^2, shape ``(3n, 3n)``.
        excitations: Excitation energies, Hartree, shape ``(m,)``. Oscillator
            strengths are not read: their table changes between versions.
        final_geometry: Last geometry, ``None`` when the run wrote none.
        terminated_normally: Whether ORCA printed its normal termination line.
        files: Names of the output files actually read.
    """

    energy: float | None = None
    forces: np.ndarray | None = None
    dipole: np.ndarray | None = None
    charges: dict[str, np.ndarray] = field(default_factory=dict)
    orbital_energies: np.ndarray | None = None
    occupations: np.ndarray | None = None
    frequencies: np.ndarray | None = None
    hessian: np.ndarray | None = None
    excitations: np.ndarray | None = None
    final_geometry: Atoms | None = None
    terminated_normally: bool = False
    files: tuple[str, ...] = ()


def _section(text: str, title: str) -> list[str]:
    """Return the lines following ``title``, up to the end of the file."""
    start = text.find(title)
    return [] if start < 0 else text[start:].splitlines()[1:]


def _rows(lines: list[str], row: re.Pattern[str]) -> list[tuple[float, ...]]:
    """Return the numbers of the consecutive lines matching ``row``.

    Lines before the first match are headers and are skipped; the first
    non-matching line after them closes the table.
    """
    found: list[tuple[float, ...]] = []
    for line in lines:
        if (match := row.match(line)) is not None:
            found.append(tuple(float(value) for value in match.groups()))
        elif found:
            break
    return found


def parse_output(text: str) -> dict[str, Any]:
    """Return the quantities of ``orca.out``.

    Args:
        text: Whole content of the file.

    Returns:
        A mapping restricted to the quantities present in the file.
    """
    values: dict[str, Any] = {"terminated_normally": _TERMINATION in text}
    if energies := _FINAL_ENERGY.findall(text):
        values["energy"] = float(energies[-1])
    charges = {}
    for title, name in _CHARGE_TABLES.items():
        if rows := _rows(_section(text, title), _CHARGE_ROW):
            charges[name] = np.asarray([row[0] for row in rows])
    if charges:
        values["charges"] = charges
    if (dipole := _DIPOLE.search(text)) is not None:
        components = [float(word) for word in dipole[1].split()[:3]]
        if len(components) == 3:
            values["dipole"] = np.asarray(components)
    if rows := _rows(_section(text, _ORBITAL_TABLE), _ORBITAL_ROW):
        # Columns: OCC, E(Eh), E(eV); the dataclass keeps the Hartree one.
        values["occupations"] = np.asarray([row[0] for row in rows])
        values["orbital_energies"] = np.asarray([row[1] for row in rows])
    if rows := _rows(_section(text, _FREQUENCY_TABLE), _FREQUENCY_ROW):
        values["frequencies"] = np.asarray([row[0] for row in rows])
    if states := _STATE.findall(text):
        values["excitations"] = np.asarray([float(energy) for energy in states])
    return values


def parse_engrad(text: str) -> dict[str, Any]:
    """Return the energy and the forces of ``orca.engrad``.

    The file holds, after comment lines, the number of atoms, the energy and the
    gradient; the forces are the opposite of the gradient.

    Args:
        text: Whole content of the file.

    Returns:
        ``energy`` and ``forces``, restricted to what the file holds.

    Raises:
        ValueError: If the file announces more gradient values than it holds.
    """
    words = [
        word
        for line in text.splitlines()
        if not line.lstrip().startswith("#")
        for word in line.split()
    ]
    if not words:
        return {}
    count = int(words[0])
    values: dict[str, Any] = {"energy": float(words[1])}
    gradient = words[2 : 2 + 3 * count]
    if len(gradient) < 3 * count:
        raise ValueError(
            f"{ENGRAD_FILE}: expected {3 * count} gradient values, got {len(gradient)}"
        )
    values["forces"] = -np.asarray([float(word) for word in gradient]).reshape(count, 3)
    return values


def parse_hessian(text: str) -> dict[str, Any]:
    """Return the Hessian and the frequencies of ``orca.hess``.

    The ``$hessian`` block is written by column groups: a line of column indices,
    then one line per row starting with its index.

    Args:
        text: Whole content of the file.

    Returns:
        ``hessian`` and ``frequencies``, restricted to what the file holds.
    """
    values: dict[str, Any] = {}
    if (matrix := _hessian_matrix(_section(text, "$hessian"))) is not None:
        values["hessian"] = matrix
    rows = _rows(_section(text, "$vibrational_frequencies"), _FREQUENCY_PAIR)
    if rows:
        values["frequencies"] = np.asarray([row[0] for row in rows])
    return values


def _hessian_matrix(lines: list[str]) -> np.ndarray | None:
    """Return the square matrix of a ``$hessian`` block, ``None`` when absent."""
    size = None
    matrix: np.ndarray | None = None
    columns: list[int] = []
    for line in lines:
        words = line.split()
        if not words:
            continue
        if size is None:
            size = int(words[0])
            matrix = np.zeros((size, size))
            continue
        if line.startswith("$"):
            break
        if all(word.lstrip("-").isdigit() for word in words):
            columns = [int(word) for word in words]
            continue
        row = int(words[0])
        for column, value in zip(columns, words[1:], strict=False):
            matrix[row, column] = float(value)
    return matrix


def parse_directory(directory: Path, basename: str = "orca") -> OrcaOutput:
    """Read every known output file of ``directory``.

    A missing file is not an error: the corresponding attributes stay ``None``.
    ``orca.out`` gives the energy, the populations and the spectra; ``orca.engrad``
    the forces; ``orca.hess`` the Hessian.

    Args:
        directory: Directory of the run.
        basename: Base name of the files, ``"orca"`` as AMAC writes them.

    Returns:
        The values read, in program units.
    """
    directory = Path(directory)
    values: dict[str, Any] = {}
    read_files: list[str] = []

    def content(suffix: str) -> str | None:
        path = directory / f"{basename}{suffix}"
        if not path.is_file():
            return None
        read_files.append(path.name)
        return path.read_text(encoding="utf-8", errors="replace")

    if (text := content(".out")) is not None:
        values |= parse_output(text)
    if (text := content(".engrad")) is not None:
        # The gradient file is the only source of forces, and its energy agrees
        # with the one of the log: it fills the energy only when it is missing.
        engrad = parse_engrad(text)
        values["forces"] = engrad.get("forces")
        values.setdefault("energy", engrad.get("energy"))
    if (text := content(".hess")) is not None:
        for key, value in parse_hessian(text).items():
            values.setdefault(key, value)
    for name in (f"{basename}.xyz", f"{basename}_trj.xyz"):
        if (directory / name).is_file():
            read_files.append(name)
            values["final_geometry"] = read(directory / name, index=-1)
            break
    return OrcaOutput(**values, files=tuple(read_files))
