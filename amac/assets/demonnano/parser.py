"""Reading of the deMonNano results, as pure functions.

Two sources give the same :class:`DemonNanoOutput`: the ``results`` dictionary of
``deMonPy`` right after a run (:func:`from_results`), and the files left in the run
directory (:func:`parse_directory`), so that handlers keep working when
``amac.reprocess`` runs without the library.

Values keep the units of the program: Hartree for energies, Hartree/Bohr for
gradients and forces, Angstrom for geometries, elementary charges for populations.
The handlers of ``amac.assets.demonnano.handlers`` convert them to ASE units.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from ase import Atoms

OUTPUT_FILE = "deMon.out"
GEOMETRY_FILE = "deMon.mol"
FORCES_FILE = "forces.out"

# "DFTB total energy       :     -4.0710651894" and the other labelled terms.
_ENERGY_LABELS = {
    "DFTB total energy": "energy",
    "DFTB electronic energy": "electronic_energy",
    "DFTB band energy": "band_energy",
    "DFTB repulsive energy": "repulsive_energy",
    "DFTB Coulomb energy": "coulomb_energy",
    "DFTB London energy": "london_energy",
    "DFTB electronic entropy": "electronic_entropy",
    "DFTB HOMO-LUMO gap": "homo_lumo_gap",
    "DFTB Fermi energy level": "fermi_energy",
}
_GRADIENT_HEADER = "CARTESIAN GRADIENT"
_DIPOLE = re.compile(
    r"charge dipole\s*=\s*([-+\d.eE]+)\s+([-+\d.eE]+)\s+([-+\d.eE]+)"
)
_OCCUPIED = "Occupied Eigen values"
_VIRTUAL = "Virtual Eigen values"
_NUMBER = re.compile(r"[-+]?\d*\.\d+(?:[eE][-+]?\d+)?")
_NOT_CONVERGED = "optimization not converged"
_ERROR = "ERROR :"


@dataclass(frozen=True)
class DemonNanoOutput:
    """Values of one deMonNano run, in program units.

    Attributes:
        energy: Total DFTB energy, Hartree.
        energies: Every labelled energy term of ``deMon.out``, Hartree.
        forces: Forces, Hartree/Bohr, shape ``(n, 3)``; the opposite of the
            gradient, and ``None`` unless the run printed one.
        charges: Mulliken charges, elementary charges, shape ``(n,)``.
        dipole: Charge dipole as printed by the program, shape ``(3,)``; its unit
            is assumed to be atomic units (placeholder P19).
        orbital_energies: Occupied then virtual eigenvalues, Hartree, written only
            with ``PRINT MOE``.
        final_geometry: Last geometry of the run, Angstrom.
        trajectory: Every geometry of the run, first to last.
        converged: ``False`` when the run reports a failed optimisation, ``True``
            when it reports none, ``None`` when nothing is stated.
        errors: Error lines reported by the program or the library.
        files: Names of the files actually read.
    """

    energy: float | None = None
    energies: dict[str, float] = field(default_factory=dict)
    forces: np.ndarray | None = None
    charges: np.ndarray | None = None
    dipole: np.ndarray | None = None
    orbital_energies: np.ndarray | None = None
    final_geometry: Atoms | None = None
    trajectory: tuple[Atoms, ...] = ()
    converged: bool | None = None
    errors: tuple[str, ...] = ()
    files: tuple[str, ...] = ()


def parse_energies(text: str) -> dict[str, float]:
    """Return the labelled energy terms of ``deMon.out``, in Hartree.

    Args:
        text: Content of ``deMon.out``.

    Returns:
        The terms of :data:`_ENERGY_LABELS` found, keyed by normalized name; the
        last occurrence wins, which is the converged one.
    """
    found: dict[str, float] = {}
    for line in text.splitlines():
        for label, name in _ENERGY_LABELS.items():
            if label in line:
                with_value = line.split()
                try:
                    found[name] = float(with_value[-1])
                except (IndexError, ValueError):
                    continue
    return found


def parse_gradient(text: str) -> np.ndarray | None:
    """Return the last ``CARTESIAN GRADIENT`` block, Hartree/Bohr, shape ``(n, 3)``.

    The block is written only when ``PRINT GRAD`` is active. Each row is
    ``index symbol gx gy gz``; the block ends on the first line that holds
    anything else.

    Args:
        text: Content of ``deMon.out``.

    Returns:
        The gradient, or ``None`` when no complete block is found.
    """
    rows: list[list[float]] = []
    reading = False
    for line in text.splitlines():
        if _GRADIENT_HEADER in line:
            reading, rows = True, []
            continue
        if not reading:
            continue
        tokens = line.split()
        if len(tokens) >= 5:
            try:
                rows.append([float(value) for value in tokens[2:5]])
            except ValueError:
                reading = False
        elif rows:
            reading = False
    return np.array(rows) if rows else None


def parse_dipole(text: str) -> np.ndarray | None:
    """Return the ``charge dipole`` vector of ``deMon.out``, shape ``(3,)``."""
    match = _DIPOLE.search(text)
    return None if match is None else np.array([float(v) for v in match.groups()])


def parse_orbital_energies(text: str) -> np.ndarray | None:
    """Return the eigenvalues printed with ``PRINT MOE``, Hartree.

    Occupied levels come first, then the virtual ones, in the order of the file.
    """
    values: list[float] = []
    for line in text.splitlines():
        if _OCCUPIED in line or _VIRTUAL in line:
            values.extend(float(number) for number in _NUMBER.findall(line))
    return np.array(values) if values else None


def parse_errors(text: str) -> tuple[tuple[str, ...], bool | None]:
    """Return the error lines of ``deMon.out`` and whether the run converged.

    Returns:
        The messages reported by the program, and ``False`` when it states that
        the optimisation did not converge, ``True`` when the run ended normally
        with an energy, ``None`` when neither is stated.
    """
    messages = [
        line.split(_ERROR)[-1].strip() for line in text.splitlines() if _ERROR in line
    ]
    converged: bool | None = None
    if _NOT_CONVERGED in text:
        converged, messages = False, [*messages, _NOT_CONVERGED]
    elif any(label in text for label in _ENERGY_LABELS):
        converged = True
    return tuple(messages), converged


def parse_forces_file(text: str) -> np.ndarray | None:
    """Return the forces of ``forces.out``, Hartree/Bohr, shape ``(n, 3)``.

    The file is written by an optimisation asked with ``SP``; its first line is a
    header, then one row of three components per atom.
    """
    rows: list[list[float]] = []
    for line in text.splitlines()[1:]:
        tokens = line.split()
        if len(tokens) < 3:
            continue
        try:
            rows.append([float(value) for value in tokens[-3:]])
        except ValueError:
            continue
    return np.array(rows) if rows else None


def parse_geometries(text: str) -> list[Atoms]:
    """Return every geometry of ``deMon.mol``, Angstrom.

    The file is xyz with an optional fifth column holding the Mulliken charge of
    the atom, which is kept in ``Atoms.get_initial_charges()``. Dummy atoms
    (``Xx``), which carry the lattice, are dropped: deMonNano is molecular here.

    Args:
        text: Content of ``deMon.mol``.

    Returns:
        The geometries, in the order of the file.
    """
    lines = [line for line in text.splitlines() if line.strip()]
    images: list[Atoms] = []
    index = 0
    while index < len(lines):
        try:
            count = int(lines[index].split()[0])
        except (IndexError, ValueError):
            break
        rows = lines[index + 2 : index + 2 + count]
        index += 2 + count
        symbols, positions, charges = [], [], []
        for row in rows:
            tokens = row.split()
            if len(tokens) < 4 or tokens[0].capitalize() == "Xx":
                continue
            symbols.append(tokens[0].capitalize())
            positions.append([float(value) for value in tokens[1:4]])
            charges.append(float(tokens[4]) if len(tokens) > 4 else 0.0)
        if symbols:
            atoms = Atoms(symbols, positions=positions)
            atoms.set_initial_charges(charges)
            images.append(atoms)
    return images


def from_results(results: Mapping[str, Any]) -> DemonNanoOutput:
    """Return the normalized output of the ``results`` of ``deMonPy``.

    The library returns its own nested dictionary; only the entries AMAC exposes
    are kept, in the units of the program. What the library does not hold, such as
    the gradient, stays ``None``: :func:`parse_directory` reads it from the files.

    Args:
        results: ``calc.results`` of a ``deMonNano`` or ``Module_DeMonNano``.

    Returns:
        The values of the run.
    """
    energies = {
        name: float(value)
        for name, value in (results.get("energy") or {}).items()
        if isinstance(value, int | float)
    }
    trajectory = tuple(_atoms_only(results.get("trajectory")))
    final = results.get("output_geometry")
    errors = tuple(
        f"[{entry.get('kind', '?')}] {entry.get('message', '')}".strip()
        if isinstance(entry, Mapping)
        else str(entry)
        for entry in results.get("errors") or ()
    )
    return DemonNanoOutput(
        energy=energies.get("energy"),
        energies=energies,
        forces=_array(results.get("forces")),
        charges=_charges(final),
        orbital_energies=_eigenvalues(results.get("moe")),
        final_geometry=final if isinstance(final, Atoms) else None,
        trajectory=trajectory,
        converged=results.get("converged"),
        errors=errors,
    )


def parse_directory(directory: Path) -> DemonNanoOutput:
    """Read the files of a run directory into a :class:`DemonNanoOutput`.

    ``deMon.out`` gives the energies, the gradient, the dipole and the
    eigenvalues; ``deMon.mol`` the geometries and the Mulliken charges;
    ``forces.out`` the forces when an optimisation wrote them, which win over the
    gradient. A missing file is not an error: the attributes stay ``None``.

    Args:
        directory: Directory of the run.

    Returns:
        The values read, in program units.
    """
    directory = Path(directory)
    read_files: list[str] = []

    def content(name: str) -> str | None:
        path = directory / name
        if not path.is_file():
            return None
        read_files.append(name)
        return path.read_text(encoding="utf-8", errors="replace")

    values: dict[str, Any] = {}
    if (text := content(OUTPUT_FILE)) is not None:
        energies = parse_energies(text)
        errors, converged = parse_errors(text)
        gradient = parse_gradient(text)
        values |= {
            "energy": energies.get("energy"),
            "energies": energies,
            "forces": None if gradient is None else -gradient,
            "dipole": parse_dipole(text),
            "orbital_energies": parse_orbital_energies(text),
            "converged": converged,
            "errors": errors,
        }
    if (text := content(FORCES_FILE)) is not None:
        if (forces := parse_forces_file(text)) is not None:
            values["forces"] = forces
    if (text := content(GEOMETRY_FILE)) is not None:
        if images := parse_geometries(text):
            values["trajectory"] = tuple(images)
            values["final_geometry"] = images[-1]
            values["charges"] = images[-1].get_initial_charges()
    return DemonNanoOutput(**values, files=tuple(read_files))


def _array(value: Any) -> np.ndarray | None:
    return None if value is None else np.asarray(value, dtype=float)


def _atoms_only(value: Any) -> list[Atoms]:
    """Return the ``Atoms`` of a trajectory; the library also returns other shapes."""
    if not isinstance(value, Sequence) or isinstance(value, str):
        return []
    return [image for image in value if isinstance(image, Atoms)]


def _charges(geometry: Any) -> np.ndarray | None:
    """Return the Mulliken charges carried by the geometry of the library."""
    if not isinstance(geometry, Atoms):
        return None
    charges = geometry.get_initial_charges()
    return charges if np.any(charges) else None


def _eigenvalues(moe: Any) -> np.ndarray | None:
    """Return the occupied then virtual eigenvalues of ``results["moe"]``."""
    if not isinstance(moe, Mapping):
        return None
    values = [*(moe.get("occupied") or ()), *(moe.get("virtual") or ())]
    return np.array(values, dtype=float) if values else None
