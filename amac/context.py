"""Runtime context and result of a single calculation."""

from __future__ import annotations

import copy

import time
from datetime import date

from collections.abc import Callable
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import TYPE_CHECKING, Any, Self

from ase import Atoms

from amac.asset import resolved_software
from amac.engine.software import Software
from amac.engine.execute import Execute


@dataclass
class base:

    def __call__(self, **kwargs):
        for key,item in kwargs.items():
            if key in self.__dict__.keys():
                self.__setattr__(key, item)

    def to_dict(self) -> dict[str, Any]:
        """Return the result as a dict, without the context."""
        results = {}
        for key,item in self.__dict__.items():
            value = copy.deepcopy(item)
            if hasattr(item, "to_dict"):
                value = item.to_dict()
            results.update({
                key:value
            })
        return results

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




@dataclass
class Properties(base):
    """Properties of calculation

    Attributes:
        image: Geometry of the image (ase.Atoms).
        method: method used
        method_args: properties associated with method
        module: module used
        module_args: properties associated with module
    """

    image: Atoms = None
    method: str = None
    method_args: dict[str, Any] = field(default_factory=dict)
    module: str = None
    module_args: dict[str, Any] = field(default_factory=dict)
    handler: tuple = ()




@dataclass
class Explorer(base):

    input_files: dict[str, Path] = field(default_factory=dict)
    output_files: dict[str, Path] = field(default_factory=dict)
    annexe_files: dict[str, Path] = field(default_factory=dict)



@dataclass
class Context(base):
    """Mutable state shared by the steps of calculation.

    Attributes:
        image: Geometry of the image (ase.Atoms).
        software: Software of computation.
        soft_spec: Software specification.
        execute: Execution of computation.
        exec_spec: Execution specification.
        workdir: Working directory of the image.
        stdout: Standard output of the run.
        stderr: Standard error of the run.
        metadata: Free-form additional information.
    """

    software: type[Software] | str | None = None
    soft_spec: dict[str, Path] = field(default_factory=dict)
    execute: type[Execute] = None
    exec_spec: dict[str, Path] = field(default_factory=dict)
    workdir: Path | None = None
    stdout: str | None = None
    stderr: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.workdir = Path(self.workdir)

        if isinstance(self.software,str):
            _soft = resolved_software(self.software, **self.soft_spec)
            self.software = _soft


@dataclass
class Duration(base):

    date_begin: None = None
    date_end: None = None
    date_steps: None = None
    duree: None = None
    _time_start: None = None
    _time_stop: None = None

    def _open(self):
        self._time_start = time.time()
        self.date_begin = date.today()

    def _closed(self):
        self._time_stop = time.time()
        self.date_end = date.today()
        self.duree = self._time_stop - self._time_start


@dataclass
class Result(base):
    """Outcome of a calculation on one image.

    Attributes:
        complet: State of calculation.
        success: Final state of calculation.
        errors: Errors collected during the run.
        product: production of calculation according to handler
        return_code: error code 
    """
    complet: bool = False
    success: bool = False
    errors: list[Any] = field(default_factory=list)
    return_code: int | None = None
    product: dict[str, Any] = field(default_factory=dict)






















