"""Reading of the DFTB+ output files, as pure functions.

Every function takes text (or a path for the binary-free geometry files) and
returns plain data, so that the parsers are testable without DFTB+ and without a
``RunContext``. :func:`parse_directory` gathers them in a :class:`DftbPlusOutput`.

Values keep the units of the program: Hartree for energies, Bohr for lengths,
Hartree/Bohr for forces, elementary charges for populations. The handlers of
``amac.assets.dftbplus.handlers`` convert them to ASE units.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from ase import Atoms
from ase.io import read
from ase.units import Hartree

RESULTS_TAG = "results.tag"
DETAILED_OUT = "detailed.out"
BAND_OUT = "band.out"
HESSIAN_OUT = "hessian.out"
BORN_OUT = "born.out"
MD_OUT = "md.out"
EXCITATIONS = "EXC.DAT"
FINAL_GEOMETRY = ("geo_end.gen", "geo_end.xyz")

# "name:type:rank:shape" header of a block of results.tag, e.g. "forces:real:2:3,3".
_TAG_HEADER = re.compile(
    r"^(?P<name>\S+)\s*:(?P<type>real|integer|complex|logical):"
    r"(?P<rank>\d+):(?P<shape>[\d,]*)\s*$"
)
_TAG_VALUES = {"real": float, "integer": int, "logical": lambda text: text == "T"}
# "Total energy:  -3.9422656585 H  ..." in detailed.out; only the first number is read.
_LABELLED = re.compile(r"^\s*(?P<label>[^:]+?)\s*:\s*(?P<value>[-+]?[\d.]+(?:[eEdD][-+]?\d+)?)")
_DETAILED_LABELS = {
    "Total energy": "energy",
    "Total Mermin free energy": "mermin_free_energy",
    "Band energy": "band_energy",
    "Total energy contribution from dispersion": "dispersion_energy",
    "Repulsive energy": "repulsive_energy",
    "Fermi level": "fermi_level",
}
_CONVERGED = "SCC converged"


@dataclass(frozen=True)
class DftbPlusOutput:
    """Values read in the output files of one DFTB+ run, in program units.

    Attributes:
        energy: Total energy, Hartree.
        mermin_free_energy: Mermin free energy, Hartree.
        band_energy: Band structure energy, Hartree.
        repulsive_energy: Repulsive energy, Hartree.
        dispersion_energy: Dispersion energy, Hartree, ``None`` without dispersion.
        forces: Forces, Hartree/Bohr, shape ``(n, 3)``.
        charges: Net atomic charges (Mulliken), elementary charges, shape ``(n,)``.
        dipole: Dipole moment, atomic units, shape ``(3,)``.
        eigenvalues: Orbital energies, Hartree, shape ``(spins, kpoints, bands)``.
        occupations: Occupations of ``eigenvalues``, same shape.
        fermi_level: Fermi level, Hartree.
        stress: Stress tensor, atomic units, shape ``(3, 3)``.
        hessian: Second derivatives, Hartree/Bohr², shape ``(3n, 3n)``.
        born_charges: Born effective charges, atomic units, shape ``(n, 3, 3)``.
        final_geometry: Last geometry, ``None`` when the run wrote none.
        md_steps: Rows read in ``md.out``, keyed by quantity.
        excitations: Excitation energies (Hartree) and oscillator strengths of
            ``EXC.DAT``, shape ``(m, 2)``.
        converged: Whether the SCC cycle converged, ``None`` when not stated.
        files: Names of the output files actually read.
    """

    energy: float | None = None
    mermin_free_energy: float | None = None
    band_energy: float | None = None
    repulsive_energy: float | None = None
    dispersion_energy: float | None = None
    forces: np.ndarray | None = None
    charges: np.ndarray | None = None
    dipole: np.ndarray | None = None
    eigenvalues: np.ndarray | None = None
    occupations: np.ndarray | None = None
    fermi_level: float | None = None
    stress: np.ndarray | None = None
    hessian: np.ndarray | None = None
    born_charges: np.ndarray | None = None
    final_geometry: Atoms | None = None
    md_steps: dict[str, np.ndarray] = field(default_factory=dict)
    excitations: np.ndarray | None = None
    converged: bool | None = None
    files: tuple[str, ...] = ()


def parse_tagged(text: str) -> dict[str, Any]:
    """Return the blocks of a tagged file (``results.tag``, ``autotest.tag``).

    Each block starts with a ``name:type:rank:shape`` header followed by its values,
    written free-form on the next lines. A rank of 0 gives a scalar, a higher rank
    an array reshaped in Fortran order, as DFTB+ writes it.

    Args:
        text: Whole content of the file.

    Returns:
        The blocks keyed by name, values as ``float``, ``int``, ``bool`` or
        ``numpy.ndarray``.

    Raises:
        ValueError: If a block holds fewer values than its shape announces.
    """
    blocks: dict[str, Any] = {}
    name = None
    for line in text.splitlines():
        if (header := _TAG_HEADER.match(line)) is not None:
            name = header["name"]
            shape = [int(n) for n in header["shape"].split(",") if n]
            blocks[name] = (header["type"], shape, [])
            continue
        if name is not None and line.strip():
            blocks[name][2].extend(line.split())
    return {key: _tag_value(key, *block) for key, block in blocks.items()}


def _tag_value(name: str, kind: str, shape: list[int], words: list[str]) -> Any:
    convert = _TAG_VALUES.get(kind)
    if convert is None:  # complex: real and imaginary parts alternate.
        values = [complex(float(re_), float(im)) for re_, im in zip(*[iter(words)] * 2)]
    else:
        values = [convert(word) for word in words]
    if not shape:
        return values[0]
    expected = int(np.prod(shape))
    if len(values) < expected:
        raise ValueError(f"{name}: expected {expected} values, got {len(values)}")
    # The header gives the fastest index first ("3,2" for the forces of two atoms),
    # so reversing the shape reads the values as written: one atom per row.
    return np.asarray(values[:expected]).reshape(shape[::-1])


def parse_results_tag(text: str) -> dict[str, Any]:
    """Return the quantities of ``results.tag`` under the names of the dataclass.

    Args:
        text: Content of ``results.tag``.

    Returns:
        A mapping restricted to the blocks present in the file.
    """
    blocks = parse_tagged(text)
    names = {
        "total_energy": "energy",
        "mermin_energy": "mermin_free_energy",
        "band_energy": "band_energy",
        "repulsive_energy": "repulsive_energy",
        "forces": "forces",
        "gross_atomic_charges": "charges",
        "dipole_moments": "dipole",
        "eigenvalues": "eigenvalues",
        "filling": "occupations",
        "fermi_level": "fermi_level",
        "stress": "stress",
        "hessian_numerical": "hessian",
        "born_charges": "born_charges",
    }
    values = {names[key]: value for key, value in blocks.items() if key in names}
    if (dipole := values.get("dipole")) is not None:
        values["dipole"] = np.asarray(dipole).reshape(-1)[:3]
    if (energy := values.get("energy")) is not None:
        values["energy"] = float(np.asarray(energy).reshape(-1)[0])
    return values


def parse_detailed_out(text: str) -> dict[str, Any]:
    """Return the labelled energies, charges, forces and dipole of ``detailed.out``.

    Only the quantities AMAC exposes are read; the file also holds tables that
    ``results.tag`` gives in machine-readable form.

    Args:
        text: Content of ``detailed.out``.

    Returns:
        A mapping restricted to the quantities present in the file.
    """
    values: dict[str, Any] = {}
    for line in text.splitlines():
        if (found := _LABELLED.match(line)) is not None:
            key = _DETAILED_LABELS.get(found["label"].strip())
            if key is not None and key not in values:
                values[key] = float(found["value"].replace("D", "E"))
    if _CONVERGED in text:
        values["converged"] = True
    elif "SCC is NOT converged" in text:
        values["converged"] = False
    if (forces := _table(text, "Total Forces")) is not None:
        # Each row is "index fx fy fz" in recent versions, "fx fy fz" before.
        values["forces"] = forces[:, -3:]
    if (charges := _table(text, "Net atomic charges (e)")) is not None:
        values["charges"] = charges[:, -1]
    if (dipole := re.search(r"Dipole moment:\s+([-\d.eE+ ]+)au", text)) is not None:
        values["dipole"] = np.asarray([float(x) for x in dipole[1].split()])
    return values


def _table(text: str, title: str) -> np.ndarray | None:
    """Return the rows of numbers following ``title``, ``None`` when absent."""
    start = text.find(title)
    if start < 0:
        return None
    rows = []
    for line in text[start:].splitlines()[1:]:
        words = line.split()
        try:
            row = [float(word) for word in words]
        except ValueError:
            if rows:
                break
            continue  # Header lines between the title and the numbers.
        if row:
            rows.append(row)
        elif rows:
            break
    return np.asarray(rows) if rows else None


def parse_band_out(text: str) -> tuple[np.ndarray, np.ndarray] | None:
    """Return the eigenvalues and occupations of ``band.out``.

    Args:
        text: Content of ``band.out``.

    Returns:
        ``(eigenvalues, occupations)`` with shape ``(kpoints, bands)``, in eV as
        DFTB+ writes this file, or ``None`` when no band is found.
    """
    energies: list[list[float]] = []
    occupations: list[list[float]] = []
    for line in text.splitlines():
        words = line.split()
        if words[:1] == ["KPT"]:
            energies.append([])
            occupations.append([])
            continue
        if len(words) == 3 and energies:
            _, energy, occupation = words
            energies[-1].append(float(energy))
            occupations[-1].append(float(occupation))
    if not energies:
        return None
    return np.asarray(energies), np.asarray(occupations)


def parse_matrix(text: str) -> np.ndarray | None:
    """Return the flat numbers of ``hessian.out`` or ``born.out`` as one array.

    The caller reshapes them: ``(3n, 3n)`` for the Hessian, ``(n, 3, 3)`` for the
    Born charges.

    Args:
        text: Content of the file.

    Returns:
        The values in file order, or ``None`` when the file holds no number.
    """
    values = [float(word) for line in text.splitlines() for word in line.split()]
    return np.asarray(values) if values else None


def parse_md_out(text: str) -> dict[str, np.ndarray]:
    """Return the per-step quantities of ``md.out``.

    Args:
        text: Content of ``md.out``.

    Returns:
        Arrays keyed by the label written by DFTB+ (e.g. ``"Total MD Energy"``),
        one value per step; empty when the file holds no labelled value.
    """
    steps: dict[str, list[float]] = {}
    for line in text.splitlines():
        if (found := _LABELLED.match(line)) is not None:
            steps.setdefault(found["label"].strip(), []).append(
                float(found["value"].replace("D", "E"))
            )
    return {label: np.asarray(values) for label, values in steps.items()}


def parse_excitations(text: str) -> np.ndarray | None:
    """Return the excitations of ``EXC.DAT``.

    Args:
        text: Content of ``EXC.DAT``.

    Returns:
        Rows ``(energy, oscillator strength)``, energies in eV as DFTB+ writes
        them, or ``None`` when the file holds no excitation.
    """
    rows = []
    for line in text.splitlines():
        words = line.split()
        if len(words) >= 2:
            try:
                rows.append([float(words[0]), float(words[1])])
            except ValueError:
                continue  # Header and separator lines.
    return np.asarray(rows) if rows else None


def parse_directory(directory: Path) -> DftbPlusOutput:
    """Read every known output file of ``directory``.

    ``results.tag`` is preferred for the quantities it holds, being machine
    readable; ``detailed.out`` completes it. A missing file is not an error: the
    corresponding attributes stay ``None``.

    Args:
        directory: Directory of the run.

    Returns:
        The values read, in program units.
    """
    directory = Path(directory)
    values: dict[str, Any] = {}
    read_files: list[str] = []

    def content(name: str) -> str | None:
        path = directory / name
        if not path.is_file():
            return None
        read_files.append(name)
        return path.read_text(encoding="utf-8", errors="replace")

    if (text := content(DETAILED_OUT)) is not None:
        values |= parse_detailed_out(text)
    if (text := content(RESULTS_TAG)) is not None:
        values |= parse_results_tag(text)
    if values.get("eigenvalues") is None and (text := content(BAND_OUT)) is not None:
        if (bands := parse_band_out(text)) is not None:
            # band.out is written in eV: bring it back to the Hartree of the dataclass.
            values["eigenvalues"], values["occupations"] = bands[0] / Hartree, bands[1]
    if (text := content(HESSIAN_OUT)) is not None:
        if (flat := parse_matrix(text)) is not None:
            size = int(round(len(flat) ** 0.5))
            values["hessian"] = flat.reshape(size, size)
    if (text := content(BORN_OUT)) is not None:
        if (flat := parse_matrix(text)) is not None:
            values["born_charges"] = flat.reshape(-1, 3, 3)
    if (text := content(MD_OUT)) is not None:
        values["md_steps"] = parse_md_out(text)
    if (text := content(EXCITATIONS)) is not None:
        if (rows := parse_excitations(text)) is not None:
            # EXC.DAT is written in eV; only the energy column is converted.
            values["excitations"] = rows / np.asarray([Hartree, 1.0])
    for name in FINAL_GEOMETRY:
        if (directory / name).is_file():
            read_files.append(name)
            values["final_geometry"] = read(directory / name)
            break
    return DftbPlusOutput(**values, files=tuple(read_files))
