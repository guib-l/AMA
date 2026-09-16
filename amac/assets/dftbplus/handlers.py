"""Handlers of DFTB+, reading its normalized output.

They read :class:`~amac.assets.dftbplus.parser.DftbPlusOutput` through
``cached_output``: the one stored by a collecting driver, or the one parsed from
the files of the run. ``DftbPlusOutput`` keeps the units of DFTB+ (Hartree,
Bohr); the handlers convert them to ASE units (eV, Å), as decided in D7.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from ase.units import Bohr, Hartree

from amac.assets.dftbplus.dftbplus import DftbPlus  # Registers DFTBP first.
from amac.assets.dftbplus.parser import DETAILED_OUT, DftbPlusOutput, parse_directory
from amac.engine.context import cached_output
from amac.engine.handlers import handler

if TYPE_CHECKING:
    from ase import Atoms

    from amac.engine.context import RunContext

__all__ = [
    "DftbPlus",
    "charges",
    "dipole",
    "energy",
    "final_geometry",
    "forces",
    "orbital_energies",
]

# One pattern only: requires_files is a conjunction, and a run may write either
# detailed.out or results.tag. detailed.out is the one DFTB+ writes by default.
_RESULTS = (DETAILED_OUT,)


def _output(ctx: RunContext) -> DftbPlusOutput:
    return cached_output(ctx, parse_directory)


@handler(software="DFTBP", requires_files=_RESULTS)
def energy(ctx: RunContext) -> float | None:
    """Return the total energy in eV, ``None`` when the run wrote none."""
    value = _output(ctx).energy
    return None if value is None else value * Hartree


@handler(software="DFTBP", requires_files=_RESULTS)
def forces(ctx: RunContext) -> np.ndarray | None:
    """Return the forces in eV/Å, shape ``(n, 3)``."""
    value = _output(ctx).forces
    return None if value is None else np.asarray(value) * (Hartree / Bohr)


@handler(software="DFTBP", requires_files=_RESULTS)
def charges(ctx: RunContext) -> np.ndarray | None:
    """Return the net atomic charges in elementary charges, shape ``(n,)``."""
    value = _output(ctx).charges
    return None if value is None else np.asarray(value)


@handler(software="DFTBP", requires_files=_RESULTS)
def dipole(ctx: RunContext) -> np.ndarray | None:
    """Return the dipole moment in e·Å, shape ``(3,)``."""
    value = _output(ctx).dipole
    return None if value is None else np.asarray(value) * Bohr


@handler(software="DFTBP", requires_files=_RESULTS)
def orbital_energies(ctx: RunContext) -> np.ndarray | None:
    """Return the orbital energies in eV, as shaped by the file they come from."""
    value = _output(ctx).eigenvalues
    return None if value is None else np.asarray(value) * Hartree


@handler(
    software="DFTBP",
    modules=("GEOMETRY_OPTIMISATION", "GEOMETRY_OPTIMISATION_LEGACY", "MOLECULAR_DYNAMICS"),
)
def final_geometry(ctx: RunContext) -> Atoms | None:
    """Return the last geometry of the run, in Å, ``None`` when none was written."""
    return _output(ctx).final_geometry
