


from pathlib import Path
from typing import *






class AMAC:

    def __init__(
            self,
            *,
            software: str | None = None,
            cpu: int = 1,
            workdir: str | Path = '.',
            label: str | None = "AMAC-calculation",
            execution: str | None = "inprocess",
            config: str | Path | None = None
        ):
        pass

    def __repr__(self):
        pass

    def __call__(self, *args, **kwds):
        pass


    def to_dict(self):
        pass

    def from_dict(self):
        pass

    def handler_register(self, *handlers):
        ...

    def parameters_register(
            self, 
            method,
            module,
            method_args={},
            module_args={},    
        ):
        ...

    def execute(
            self,
            method: str = None,
            module: str = "single-point",
            method_args: dict[str, Any] | None = None,
            module_args: dict[str, Any] | None = None,
        ):
        ...

    def restart(self,):
        ...

    def store(self):
        raise NotImplementedError
















