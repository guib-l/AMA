"""Runtime context and result of a single calculation."""

from __future__ import annotations

import copy
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

from ase import Atoms

from amac.engine.software import Software
from amac.engine.execute import Execution




@dataclass
class Context:
    """Mutable state shared by the steps of calculation.

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
        software: Software instance running the calculation.
        duration: Time in seconds
        metadata: Free-form additional information.
        driver: Driver actually used for the run.
    """

    atoms: Atoms
    execution_spec: type[Execution]
    software_spec: type[Software]
    workdir: Path
    input_files: dict[str, Path] = field(default_factory=dict)
    files: dict[str, Path] = field(default_factory=dict)
    stdout: str | None = None
    stderr: str | None = None
    return_code: int | None = None
    duration: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.workdir = Path(self.workdir)


@dataclass
class Result:
    """Outcome of a calculation on one image.

    Attributes:
        success: Final state of calculation.
        properties: Properties of calculations
        origin: Information needed to reproduce the calculation.
        errors: Errors collected during the run.
        context: Run context, excluded from serialisation.
    """

    success: bool
    properties: dict[str, Any] = field(default_factory=dict)
    origin: dict[str, Any] = field(default_factory=dict)
    errors: list[Any] = field(default_factory=list)
    context: Context | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return the result as a dict, without the context."""
        return {
            "success": self.success,
            "properties": copy.deepcopy(self.properties),
            "origin": copy.deepcopy(self.origin),
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





















