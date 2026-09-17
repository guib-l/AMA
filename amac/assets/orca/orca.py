"""ORCA driven through ``orca.inp`` and the ``orca`` executable."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from amac.assets.orca.composer import OrcaComposer
from amac.assets.orca.drivers import OrcaCclibDriver
from amac.engine.registry import register_software
from amac.engine.software import FileIOSoftware

if TYPE_CHECKING:
    from amac.engine.context import RunContext
    from amac.parameter.schema import Schema

INPUT_FILE = "orca.inp"
STDOUT_FILE = "orca.out"


@register_software
class Orca(FileIOSoftware):
    """ORCA 6.1, registered as ``ORCA``.

    The program takes its input file as an argument and writes its log on the
    standard output, which AMAC redirects to ``orca.out``. Parallel runs require
    the executable to be given as an absolute path, which AMAC enforces for every
    software.
    """

    NAME = "ORCA"
    ALIASES = ()
    DOC = Path(__file__).with_name("doc.json")
    composer_cls = OrcaComposer
    DRIVERS = (OrcaCclibDriver,)

    def command(self, ctx: RunContext) -> list[str]:
        """Return the command running ORCA on ``orca.inp``.

        Raises:
            ExecutableNotFoundError: If no explicit source gives the executable.
        """
        return [self.require_executable(ctx.exec_spec).path, INPUT_FILE]

    def stdout_file(self, ctx: RunContext) -> Path:
        """Return ``orca.out``, which receives the log of the run."""
        return Path(STDOUT_FILE)

    def schema(self) -> Schema:
        """Return the schema of the ``doc.json``, for the composer and the drivers."""
        return self._schema()
