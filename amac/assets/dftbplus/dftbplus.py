"""DFTB+ driven through ``dftb_in.hsd`` and the ``dftb+`` executable."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from amac.assets.dftbplus.composer import DftbPlusComposer
from amac.assets.dftbplus.drivers import DftbPlusApiDriver, HsdDriver
from amac.engine.registry import register_software
from amac.engine.software import FileIOSoftware

if TYPE_CHECKING:
    from amac.engine.context import RunContext
    from amac.parameter.schema import Schema

STDOUT_FILE = "dftb.out"


@register_software
class DftbPlus(FileIOSoftware):
    """DFTB+ 25.1, registered as ``DFTBP``.

    The program reads ``dftb_in.hsd`` in its working directory and writes its log
    on the standard output, which AMAC redirects to ``dftb.out``. The Slater-Koster
    directories (``DFTB_PREFIX``, ``DFTBPLUS_PARAM_DIR``) are never guessed: they
    come from ``env=`` or from the configuration file, like every other variable.
    """

    NAME = "DFTBP"
    ALIASES = ("DFTB+",)
    DOC = Path(__file__).with_name("doc.json")
    composer_cls = DftbPlusComposer
    # "auto" tries the API first: it runs the program without an executable path.
    DRIVERS = (DftbPlusApiDriver, HsdDriver)

    def command(self, ctx: RunContext) -> list[str]:
        """Return the command running DFTB+ on ``dftb_in.hsd``.

        The program takes no argument: it reads the input file of its working
        directory, which is ``ctx.directory``.

        Raises:
            ExecutableNotFoundError: If no explicit source gives the executable.
        """
        return [self.require_executable(ctx.exec_spec).path]

    def stdout_file(self, ctx: RunContext) -> Path:
        """Return ``dftb.out``, which receives the log of the run."""
        return Path(STDOUT_FILE)

    def schema(self) -> Schema:
        """Return the schema of the ``doc.json``, for the composer and the drivers."""
        return self._schema()
