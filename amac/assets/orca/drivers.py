"""Optional library drivers of ORCA.

Only ``cclib`` is implemented: it reads ``orca.out`` and fills the normalized
output. The OPI drivers of the proposal (``opi``, ``opi-parser``) wait for the
placeholders P8 to P10 (path of the ORCA binary given to OPI, arbitrary blocks,
reading a calculation OPI did not prepare).
"""

from __future__ import annotations

from typing import Any

import numpy as np
from ase import Atoms
from ase.units import Hartree, invcm

from amac.assets._shared.cclib_driver import CclibDriver
from amac.assets.orca.parser import OUTPUT_FILE, OrcaOutput


class OrcaCclibDriver(CclibDriver):
    """Reads ``orca.out`` with cclib instead of the AMAC parser.

    cclib normalizes its own units (eV for energies, cm^-1 for excitations), while
    :class:`~amac.assets.orca.parser.OrcaOutput` keeps the units of ORCA:
    :meth:`to_output` converts them back.
    """

    OUTPUT_FILE = OUTPUT_FILE

    def to_output(self, data: Any) -> OrcaOutput:
        """Return the ``ccData`` of cclib as an :class:`OrcaOutput`.

        Attributes cclib did not find are simply absent from ``data``: each one is
        read defensively and left ``None``.

        Args:
            data: ``ccData`` returned by ``cclib.io.ccread``.

        Returns:
            The normalized output, in the units of ORCA.
        """
        values: dict[str, Any] = {"files": (self.OUTPUT_FILE,)}
        if (energies := _last(getattr(data, "scfenergies", None))) is not None:
            values["energy"] = float(energies) / Hartree
        if (grads := _last(getattr(data, "grads", None))) is not None:
            values["forces"] = -np.asarray(grads)
        if (dipole := getattr(data, "moments", None)) is not None and len(dipole) > 1:
            values["dipole"] = np.asarray(dipole[1])
        if charges := getattr(data, "atomcharges", None):
            values["charges"] = {
                name: np.asarray(value) for name, value in charges.items()
            }
        if (orbitals := _last(getattr(data, "moenergies", None))) is not None:
            values["orbital_energies"] = np.asarray(orbitals) / Hartree
        if (frequencies := getattr(data, "vibfreqs", None)) is not None:
            values["frequencies"] = np.asarray(frequencies)
        if (hessian := getattr(data, "hessian", None)) is not None:
            values["hessian"] = np.asarray(hessian)
        if (excitations := getattr(data, "etenergies", None)) is not None:
            # cclib gives excitation energies in cm^-1.
            values["excitations"] = np.asarray(excitations) * invcm / Hartree
        if (geometry := _geometry(data)) is not None:
            values["final_geometry"] = geometry
        values["terminated_normally"] = bool(getattr(data, "metadata", {}).get("success", False))
        return OrcaOutput(**values)


def _last(value: Any) -> Any:
    """Return the last step of a per-step cclib attribute, ``None`` when empty."""
    if value is None or len(value) == 0:
        return None
    return value[-1]


def _geometry(data: Any) -> Atoms | None:
    """Return the last geometry of a ``ccData``, ``None`` without coordinates."""
    coordinates = _last(getattr(data, "atomcoords", None))
    numbers = getattr(data, "atomnos", None)
    if coordinates is None or numbers is None:
        return None
    return Atoms(numbers=np.asarray(numbers), positions=np.asarray(coordinates))
