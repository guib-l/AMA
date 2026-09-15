"""Handlers of the dummy software, reading the fake ``output.json``.

Values are returned as written by the fake program: the unit convention of the
results (TODO §2) is not confirmed yet.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from amac.assets._dummy.dummy import OUTPUT_FILE
from amac.engine.handlers import handler

if TYPE_CHECKING:
    from amac.engine.context import RunContext


@handler(software="DUMMY", requires_files=(OUTPUT_FILE,))
def energy(ctx: RunContext) -> float:
    """Return the fake energy of ``output.json``, unit unchanged."""
    return _read_output(ctx)["energy"]


@handler(software="DUMMY", requires_files=(OUTPUT_FILE,))
def forces(ctx: RunContext) -> list[list[float]]:
    """Return the fake forces of ``output.json``, unit unchanged."""
    return _read_output(ctx)["forces"]


@handler(software="DUMMY", drivers=("dummy-lib",))
def native_energy(ctx: RunContext) -> float:
    """Return the energy of the native object read by ``DummyLibraryDriver``."""
    return ctx.objects["dummy_lib"].energy


def _read_output(ctx: RunContext) -> dict[str, Any]:
    with ctx.files[OUTPUT_FILE].open(encoding="utf-8") as stream:
        return json.load(stream)
