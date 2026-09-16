"""Base driver collecting the results of a software with cclib."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from amac.engine.context import OUTPUT_KEY
from amac.engine.drivers import Driver

if TYPE_CHECKING:
    from amac.engine.context import RunContext
    from amac.engine.software import Software


class CclibDriver(Driver):
    """Driver reading the log file of a software with cclib.

    Only ``collect`` goes through cclib; the other phases follow the AMAC path. A
    subclass per software sets :attr:`OUTPUT_FILE` and implements
    :meth:`to_output`. cclib is imported inside :meth:`collect` only.

    Attributes:
        OUTPUT_FILE: Name of the log file read by cclib, relative to
            ``ctx.directory``.
    """

    NAME = "cclib"
    REQUIRES = ("cclib",)
    DISTRIBUTION = "cclib"
    PHASES = frozenset({"collect"})
    OUTPUT_FILE: ClassVar[str]

    def collect(self, software: Software, ctx: RunContext) -> None:
        """Fill ``ctx.files`` with the software, then read :attr:`OUTPUT_FILE`.

        The native ``ccData`` is stored in ``ctx.objects["cclib"]`` and the
        normalized output returned by :meth:`to_output` in
        ``ctx.objects[OUTPUT_KEY]``.

        Raises:
            ValueError: If cclib cannot read :attr:`OUTPUT_FILE`.
        """
        software.collect(ctx)
        from cclib.io import ccread

        path = ctx.directory / self.OUTPUT_FILE
        data = ccread(str(path))
        if data is None:
            raise ValueError(f"cclib could not read {path}")
        ctx.objects["cclib"] = data
        ctx.objects[OUTPUT_KEY] = self.to_output(data)

    def to_output(self, data: Any) -> Any:
        """Return the normalized output of the software built from ``data``.

        Args:
            data: ``ccData`` returned by ``cclib.io.ccread``.

        Returns:
            The normalized dataclass of the software, in the units of the program.
        """
        raise NotImplementedError(f"{type(self).__name__} does not implement to_output")
