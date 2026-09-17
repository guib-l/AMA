"""Handlers of deMonNano, reading its normalized output.

They read :class:`~amac.assets.demonnano.parser.DemonNanoOutput` through
``cached_output``: the one stored by :meth:`DeMonNano.collect`, or the one parsed
from the files of the run when reprocessing. ``DemonNanoOutput`` keeps the units
of deMonNano (Hartree, Hartree/Bohr, Angstrom); the handlers convert them to ASE
units, as decided in D7.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from ase.units import Bohr, Hartree

from amac.assets.demonnano.demonnano import DeMonNano  # Registers DEMON first.
from amac.assets.demonnano.parser import (
    GEOMETRY_FILE,
    OUTPUT_FILE,
    DemonNanoOutput,
    parse_directory,
)
from amac.engine.context import cached_output
from amac.engine.handlers import handler

if TYPE_CHECKING:
    from ase import Atoms

    from amac.engine.context import RunContext

__all__ = [
    "DeMonNano",
    "charges",
    "dipole",
    "energy",
    "final_geometry",
    "forces",
]

_LOG = (OUTPUT_FILE,)
_GEOMETRY = (GEOMETRY_FILE,)
# Modules whose run moves the atoms; a single point keeps the input geometry.
_MOVING = ("GEOMETRY_OPTIMISATION", "MOLECULAR_DYNAMICS")


def _output(ctx: RunContext) -> DemonNanoOutput:
    return cached_output(ctx, parse_directory)


@handler(software="DEMON", requires_files=_LOG)
def energy(ctx: RunContext) -> float | None:
    """Return the total DFTB energy in eV, ``None`` without one."""
    value = _output(ctx).energy
    return None if value is None else value * Hartree


@handler(software="DEMON", requires_files=_LOG)
def forces(ctx: RunContext) -> np.ndarray | None:
    """Return the forces in eV/Angstrom, shape ``(n, 3)``.

    deMonNano only writes them when it is asked to: ``PRINT GRAD`` for the
    gradient of a static run, or an optimisation writing ``forces.out``. Without
    either, the result is ``None``.
    """
    value = _output(ctx).forces
    return None if value is None else np.asarray(value) * (Hartree / Bohr)


@handler(software="DEMON", requires_files=_GEOMETRY)
def charges(ctx: RunContext) -> np.ndarray | None:
    """Return the Mulliken charges in elementary charges, shape ``(n,)``."""
    value = _output(ctx).charges
    return None if value is None else np.asarray(value)


@handler(software="DEMON", requires_files=_LOG)
def dipole(ctx: RunContext) -> np.ndarray | None:
    """Return the dipole moment in e*Angstrom, shape ``(3,)``.

    The charge dipole of ``deMon.out`` is taken to be in atomic units, which is
    not confirmed by the documentation (placeholder P19).
    """
    value = _output(ctx).dipole
    return None if value is None else np.asarray(value) * Bohr


@handler(software="DEMON", requires_files=_GEOMETRY, modules=_MOVING)
def final_geometry(ctx: RunContext) -> Atoms | None:
    """Return the last geometry of the run, in Angstrom, ``None`` without one."""
    return _output(ctx).final_geometry
