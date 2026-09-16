"""Runtime context and result of a single calculation."""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

if TYPE_CHECKING:
    from ase import Atoms

    from amac.engine.software import Software
    from amac.parameter.parameters import CalculationSpec, ExecutionSpec

OUTPUT_KEY = "output"


@dataclass
class RunContext:
    """Mutable state shared by the steps of one calculation on one image.

    Attributes:
        atoms: Geometry of the image.
        spec: Calculation specification.
        exec_spec: Execution specification.
        directory: Working directory of the image.
        input_files: Input file names mapped to their path.
        files: Produced file names mapped to their path, filled after the run.
        stdout: Standard output of the run.
        stderr: Standard error of the run.
        return_code: Exit code of the run.
        objects: Native objects of in-process software or driver libraries.
        software: Software instance running the calculation.
        timings: Durations in seconds, keyed by step name.
        metadata: Free-form additional information.
        driver: Driver actually used for the run.
    """

    atoms: Atoms
    spec: CalculationSpec
    exec_spec: ExecutionSpec
    directory: Path
    input_files: dict[str, Path] = field(default_factory=dict)
    files: dict[str, Path] = field(default_factory=dict)
    stdout: str | None = None
    stderr: str | None = None
    return_code: int | None = None
    objects: dict[str, Any] = field(default_factory=dict)
    software: Software | None = None
    timings: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    driver: str = "amac"

    def __post_init__(self) -> None:
        self.directory = Path(self.directory)


@dataclass
class Result:
    """Outcome of a calculation on one image.

    Attributes:
        success: Whether the calculation succeeded.
        properties: Handler results keyed by handler name.
        provenance: Information needed to reproduce the calculation.
        errors: Errors collected during the run.
        context: Run context, excluded from serialisation.
    """

    success: bool
    properties: dict[str, Any] = field(default_factory=dict)
    provenance: dict[str, Any] = field(default_factory=dict)
    errors: list[Any] = field(default_factory=list)
    context: RunContext | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the result as a dict, without the context."""
        return {
            "success": self.success,
            "properties": copy.deepcopy(self.properties),
            "provenance": copy.deepcopy(self.provenance),
            "errors": copy.deepcopy(self.errors),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Build a result from the output of :meth:`to_dict`.

        Raises:
            ValueError: If ``data`` contains unknown keys.
        """
        known = {f.name for f in fields(cls)} - {"context"}
        if unknown := data.keys() - known:
            raise ValueError(f"Unknown Result keys: {sorted(unknown)}")
        return cls(**copy.deepcopy(data))


def cached_output[T](ctx: RunContext, parse: Callable[[Path], T]) -> T:
    """Return the normalized output of ``ctx``, parsing it once when absent.

    The normalized output is the dataclass of a software gathering the values
    read in its output files, in the units of the program; handlers convert them
    (to ASE units). A driver that collects fills ``ctx.files`` and stores this
    dataclass in ``ctx.objects[OUTPUT_KEY]``. On the AMAC path, or when
    reprocessing, the entry is absent and is rebuilt here from the files, so
    that the same handlers work with every driver.

    Args:
        ctx: Run context filled by ``collect``.
        parse: Pure function reading ``ctx.directory`` into the dataclass.

    Returns:
        ``ctx.objects[OUTPUT_KEY]``, set to ``parse(ctx.directory)`` if absent.
    """
    if OUTPUT_KEY not in ctx.objects:
        ctx.objects[OUTPUT_KEY] = parse(ctx.directory)
    return ctx.objects[OUTPUT_KEY]
