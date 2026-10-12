


from pathlib import Path
from typing import *

from amac.asset import resolved_software



class AMAC:

    def __init__(
            self,
            *,
            software: str | None = None,
            process_unit: int = 1,
            workdir: str | Path = '.',
            label: str | None = "AMAC-calculation",
            execution: str | None = "inprocess",
            config: dict = {}
        ):

        self._soft = resolved_software(
            software,
            **config
        )
        

    def __repr__(self):
        pass

    def __call__(self, *args, **kwds):
        pass


    def to_dict(self):
        pass

    def from_dict(self):
        pass


    def resolved_handler(self):
        ...

    def handler_register(self, *handlers):
        # récupère les handlers du software
        ...

    def parameters_register(
            self, 
            method,
            module,
            method_args={},
            module_args={},    
        ):
        ...
    
    def resolved_parameters(self):
        # récupère les paramètres associés au software
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
















