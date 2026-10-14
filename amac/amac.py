

import uuid
from pathlib import Path
from typing import *

from amac.asset import resolved_software

from amac.context import Context,Result
from dataclasses import dataclass


@dataclass
class Instance:

    name: str = "default_name"
    id: uuid.UUID = uuid.uuid4()
    ctx: Context = None
    res: Result = None

    def __repr__(self):
        repr = f"\n| INSTANCE - {self.id}\n|  > name: {self.name}\n"
        repr += f"|  > workdir: {self.ctx.workdir}\n"
        repr += f"|  > complet: {self.res.complet}\n"
        repr += f"|  > success: {self.res.success}\n"
        return repr

    def update(self, *, ctx, res):
        self.ctx = ctx
        self.res = res

    @classmethod
    def new_instance(
            cls, 
            name=None, 
            atoms = None,
            exec_spec = None,
            software = None,
            workdir = None,
            input_files = {},
            files = {},
            stdout = None,
            stderr = None,
            return_code = None,
            duration = {},
            metadata = None,
            success = False,
            complet = False,
            properties = {},
            origin = {},
            errors = {}
        ):
        if name is None:
            name = "default_name"
        ctx=Context(
             atoms, exec_spec, software, workdir,
             input_files, files, stdout, stderr,
             return_code, duration, metadata,                       
        )
        res = Result(
             success,
             complet,
             properties,
             errors
        )
        return cls(name=name, ctx=ctx, res=res)
    


class AMAC:

    active_ctx: Context
    active_res: Result
    instances: List[Instance]

    def __init__(
            self,
            *,
            software: str | None = None,
            process_unit: int = 1,
            workdir: str | Path = '.',
            label: str | None = "AMAC-calculation",
            execution: str | None = "inprocess",
            config_spec: dict = {}
        ):

        self._soft = resolved_software(
            software,
            **config_spec
        )

        _instance = Instance.new_instance(
            atoms = None,
            exec_spec = None,
            software = None,
            workdir = workdir,
            input_files = {},
            files = {},
            stdout = None,
            stderr = None,
            return_code = None,
            duration = {},
            metadata = None,
            success = False,
            complet = False,
            properties = {},
            origin = {},
            errors = {}
        )


        print(_instance)

    

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

    def run(
            self,
            method: str = None,
            module: str = "single-point",
            method_args: dict[str, Any] | None = None,
            module_args: dict[str, Any] | None = None,
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
















