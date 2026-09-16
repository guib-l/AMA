"""Handlers of the dummy software, reading its normalized output.

They read :class:`~amac.assets._dummy.dummy.DummyOutput` through ``cached_output``:
the one stored by a collecting driver, or the one parsed from ``output.json``. The
dummy has no real units: values are returned as written by the fake program, where
a real software converts them to ASE units.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from amac.assets._dummy.dummy import OUTPUT_FILE, parse_directory
from amac.engine.context import cached_output
from amac.engine.handlers import handler

if TYPE_CHECKING:
    from amac.engine.context import RunContext


@handler(software="DUMMY", requires_files=(OUTPUT_FILE,))
def energy(ctx: RunContext) -> float:
    """Return the fake energy of ``output.json``, unit unchanged."""
    return cached_output(ctx, parse_directory).energy


@handler(software="DUMMY", requires_files=(OUTPUT_FILE,))
def forces(ctx: RunContext) -> list[list[float]]:
    """Return the fake forces of ``output.json``, unit unchanged."""
    return cached_output(ctx, parse_directory).forces


@handler(software="DUMMY", drivers=("dummy-lib",))
def native_energy(ctx: RunContext) -> float:
    """Return the energy of the native object read by ``DummyLibraryDriver``."""
    return ctx.objects["dummy_lib"].energy
