"""In-process test software: a harmonic pair potential computed with numpy.

It exercises the ``InProcessSoftware`` path without any external dependency: no
input file, no executable. Energies and forces are in the units of the model
parameters and positions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from amac.engine.handlers import handler
from amac.engine.registry import register_software
from amac.engine.software import InProcessSoftware

if TYPE_CHECKING:
    from amac.engine.context import RunContext


@dataclass(frozen=True)
class PairModel:
    """Harmonic springs between every pair of atoms.

    ``E = stiffness / 2 * sum over the pairs of (r_ij - bond_length) ** 2``.

    Attributes:
        stiffness: Spring constant.
        bond_length: Rest length of every spring.
    """

    stiffness: float = 1.0
    bond_length: float = 1.0

    def evaluate(self, positions: np.ndarray) -> tuple[float, np.ndarray]:
        """Return the energy and the forces (minus the gradient) of ``positions``.

        Args:
            positions: Cartesian positions, shape ``(n, 3)``.

        Returns:
            The energy, and the forces with the shape of ``positions``.

        Raises:
            ValueError: If ``positions`` does not have the shape ``(n, 3)``, or if
                two atoms have the same position.
        """
        positions = np.asarray(positions, dtype=float)
        if positions.ndim != 2 or positions.shape[1] != 3:
            raise ValueError(f"positions must have shape (n, 3), got {positions.shape}")
        first, second = np.triu_indices(len(positions), k=1)
        deltas = positions[first] - positions[second]
        distances = np.linalg.norm(deltas, axis=1)
        if np.any(distances == 0.0):
            raise ValueError("two atoms have the same position")
        stretches = distances - self.bond_length
        energy = 0.5 * self.stiffness * float(np.sum(stretches**2))
        pair_forces = -self.stiffness * (stretches / distances)[:, None] * deltas
        forces = np.zeros_like(positions)
        np.add.at(forces, first, pair_forces)
        np.subtract.at(forces, second, pair_forces)
        return energy, forces


@register_software
class DummyInProcess(InProcessSoftware):
    """Test software evaluating :class:`PairModel` in the current process.

    It shares the ``doc.json`` of the file-based dummy. :meth:`build` stores the
    model in ``ctx.objects["model"]``, :meth:`compute` stores ``"energy"`` and
    ``"forces"``.
    """

    NAME = "DUMMY_INPROCESS"
    ALIASES = ("dummy-inprocess",)
    DOC = Path(__file__).with_name("doc.json")

    def build(self, ctx: RunContext) -> None:
        """Store the pair model in ``ctx.objects["model"]``."""
        ctx.objects["model"] = PairModel()

    def compute(self, ctx: RunContext) -> None:
        """Evaluate the model on ``ctx.atoms`` and print one log line."""
        energy, forces = ctx.objects["model"].evaluate(ctx.atoms.get_positions())
        ctx.objects["energy"] = energy
        ctx.objects["forces"] = forces
        # Shows that InProcessSoftware.run captures the logs in ctx.stdout.
        print(f"dummy-inprocess: {len(ctx.atoms)} atoms")

    def collect(self, ctx: RunContext) -> None:
        """Do nothing: the results are already in ``ctx.objects``."""


@handler(software="DUMMY_INPROCESS")
def energy(ctx: RunContext) -> float:
    """Return the energy computed in the current process."""
    return ctx.objects["energy"]


@handler(software="DUMMY_INPROCESS")
def forces(ctx: RunContext) -> np.ndarray:
    """Return the forces computed in the current process, shape ``(n, 3)``."""
    return ctx.objects["forces"]
