
from __future__ import annotations
import sys
import amac
from amac import config

import copy
from abc import ABC, abstractmethod
from dataclasses import fields
from typing import Any


from pathlib import Path
from typing import Any, ClassVar, Mapping, Sequence

from dataclasses import dataclass

class Software:
    """
    Base class for every software supported by AMAC.
    """

    name: ClassVar[str] = ""
    alias: ClassVar[tuple[str, ...]] = ()
    doc: ClassVar[str | None] = None
    execute: ClassVar[str] = ""
    process: ClassVar[str] = ""
    handlers: ClassVar[Mapping[str, Any]] = {}
    driver: ClassVar[tuple[str, ...]] = ()
    composer: ClassVar[Any | None] = None
    requires_executable: ClassVar[bool] = False

    def __init__(self, **kwargs) -> None:
        """
        Bind the software instance to a configuration file.

        Args:
            config_file: Path to the software configuration file.
        """
        for key,items in kwargs.items():
            setattr(self, key, items)

        self.configure()

        for key,item in type(self).__dict__.items():
            if not key.startswith("__") and not callable(item):
                setattr(self, key, getattr(type(self), key))


    def configure(self) -> None:
        """Load and apply the software configuration."""
        _config = config.CONFIGURE[self.name]

        if self.requires_executable:
            self.execute = _config["EXECUTABLE"]

    @property
    def name(self) -> str:
        """Name of the software."""
        return type(self).name

    @abstractmethod
    def collect(self):
        ...

    @abstractmethod
    def callback(self):
        ...

    @abstractmethod
    def prepare(self):
        ...

    @abstractmethod
    def calculate(self):
        ...
    
    @abstractmethod
    def run(self):
        ...

    def resolved_executable(self):
        raise NotImplementedError


    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

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



    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def pretty_print(self, files=sys.stdout):
        """Pretty-print parsed results as indented JSON.

        The output is encoded with :class:`~deMonPy.encoder.AseEncoder`
        so that NumPy arrays and ASE objects are serialisable.

        Args:
            files: Writable text stream that receives the JSON output.
                Defaults to :data:`sys.stdout`.
        """
        import json
        from amac.utils.encoder import AseEncoder

        print(
            json.dumps(
                self.to_dict(),
                indent=4,
                ensure_ascii=True,
                cls=AseEncoder,
            ),
            file=files,
        )

















