"""deMonNano, registered as ``DEMON``.

Its handlers are exposed here (``from amac.assets import demonnano``, then
``demonnano.energy``). They follow the common handler names listed in "Adding a
software" in the README, and return ASE units. The calculation runs in the
current process through the ``deMonPy`` library, which writes ``deMon.inp`` and
starts the ``deMon.x`` binary.
"""

from amac.assets.demonnano.handlers import (
    DeMonNano,
    charges,
    dipole,
    energy,
    final_geometry,
    forces,
)

__all__ = [
    "DeMonNano",
    "charges",
    "dipole",
    "energy",
    "final_geometry",
    "forces",
]
