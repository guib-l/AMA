
from __future__ import annotations

import io
import os
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar



class Software(ABC):
    """
    Base class of every software supported by AMAC.
    """

    name = ""
    alias = ()
    doc = None
    execute = ""
    handlers = {}
    driver = ()
    composer = None
    requires_executable = False

    def __init__(self) -> None:
        """
        Bind the software to a configuration file.
        """
        ...

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


