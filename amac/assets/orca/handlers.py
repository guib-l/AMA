"""Handlers of ORCA, reading its normalized output.

They read :class:`~amac.assets.orca.parser.OrcaOutput` through ``cached_output``:
the one stored by a collecting driver, or the one parsed from the files of the
run. ``OrcaOutput`` keeps the units of ORCA (Hartree, Bohr, cm^-1); the handlers
convert them to ASE units (eV, Angstrom), as decided in D7.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from ase.units import Bohr, Hartree, invcm

from amac.assets.orca.orca import Orca  # Registers ORCA first.
from amac.assets.orca.parser import (
    ENGRAD_FILE,
    HESSIAN_FILE,
    OUTPUT_FILE,
    OrcaOutput,
    parse_directory,
)
from amac.engine.context import cached_output
from amac.engine.handlers import handler

if TYPE_CHECKING:
    from ase import Atoms

    from amac.engine.context import RunContext

__all__ = [
    "Orca",
    "charges",
    "dipole",
    "energy",
    "excitations",
    "final_geometry",
    "forces",
    "frequencies",
    "hessian",
    "loewdin_charges",
    "mulliken_charges",
    "orbital_energies",
]

_LOG = (OUTPUT_FILE,)
_MULLIKEN = "mulliken"
_LOEWDIN = "loewdin"
# Modules whose run moves the atoms; the others keep the input geometry.
_MOVING = (
    "GEOMETRY_OPTIMISATION",
    "TRANSITION_STATE_SEARCH",
    "IRC",
    "NEB",
    "MOLECULAR_DYNAMICS",
    "PES_SCAN",
)


def _output(ctx: RunContext) -> OrcaOutput:
    return cached_output(ctx, parse_directory)


@handler(software="ORCA", requires_files=_LOG)
def energy(ctx: RunContext) -> float | None:
    """Return the final single point energy in eV, ``None`` without one."""
    value = _output(ctx).energy
    return None if value is None else value * Hartree


@handler(software="ORCA", requires_files=(ENGRAD_FILE,))
def forces(ctx: RunContext) -> np.ndarray | None:
    """Return the forces in eV/Angstrom, shape ``(n, 3)``."""
    value = _output(ctx).forces
    return None if value is None else np.asarray(value) * (Hartree / Bohr)


@handler(software="ORCA", requires_files=_LOG)
def charges(ctx: RunContext) -> np.ndarray | None:
    """Return the Mulliken charges in elementary charges, shape ``(n,)``."""
    return _charges(ctx, _MULLIKEN)


@handler(software="ORCA", requires_files=_LOG)
def mulliken_charges(ctx: RunContext) -> np.ndarray | None:
    """Return the Mulliken population analysis, shape ``(n,)``."""
    return _charges(ctx, _MULLIKEN)


@handler(software="ORCA", requires_files=_LOG)
def loewdin_charges(ctx: RunContext) -> np.ndarray | None:
    """Return the Loewdin population analysis, shape ``(n,)``."""
    return _charges(ctx, _LOEWDIN)


def _charges(ctx: RunContext, analysis: str) -> np.ndarray | None:
    value = _output(ctx).charges.get(analysis)
    return None if value is None else np.asarray(value)


@handler(software="ORCA", requires_files=_LOG)
def dipole(ctx: RunContext) -> np.ndarray | None:
    """Return the dipole moment in e*Angstrom, shape ``(3,)``."""
    value = _output(ctx).dipole
    return None if value is None else np.asarray(value) * Bohr


@handler(software="ORCA", requires_files=_LOG)
def orbital_energies(ctx: RunContext) -> np.ndarray | None:
    """Return the orbital energies in eV, shape ``(m,)``."""
    value = _output(ctx).orbital_energies
    return None if value is None else np.asarray(value) * Hartree


@handler(software="ORCA", requires_files=_LOG)
def frequencies(ctx: RunContext) -> np.ndarray | None:
    """Return the harmonic frequencies as energies in eV, shape ``(3n,)``.

    ORCA writes them in cm^-1; ``ase.units.invcm`` converts them, as every handler
    returns ASE units.
    """
    value = _output(ctx).frequencies
    return None if value is None else np.asarray(value) * invcm


@handler(software="ORCA", requires_files=(HESSIAN_FILE,))
def hessian(ctx: RunContext) -> np.ndarray | None:
    """Return the Hessian in eV/Angstrom^2, shape ``(3n, 3n)``."""
    value = _output(ctx).hessian
    return None if value is None else np.asarray(value) * (Hartree / Bohr**2)


@handler(software="ORCA", requires_files=_LOG)
def excitations(ctx: RunContext) -> np.ndarray | None:
    """Return the excitation energies in eV, shape ``(m,)``."""
    value = _output(ctx).excitations
    return None if value is None else np.asarray(value) * Hartree


@handler(software="ORCA", modules=_MOVING)
def final_geometry(ctx: RunContext) -> Atoms | None:
    """Return the last geometry of the run, in Angstrom, ``None`` without one."""
    return _output(ctx).final_geometry
