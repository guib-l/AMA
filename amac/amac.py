

import uuid
from pathlib import Path
from typing import *

import time
from functools import wraps
from amac.asset import resolved_software

from amac.context import Context,Result,Explorer,Duration,Properties
from amac.instance import Instance
from dataclasses import dataclass




class AMAC:

    instances: List[Instance] = []
    __active_instance: Instance 

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
            name = None, 
            image = None,
            software = software,
            soft_spec = config_spec,
            execute = None,
            exec_spec = None,
            workdir = workdir,
            input_files = {},
            output_files = {},
            annexe_files = {},
            stdout = None,
            stderr = None,
            return_code = None,
            metadata = None,
            success = False,
            complet = False,
            method = None,
            method_attr = {},
            module = None,
            module_attr = {},
            handler = (),
            errors = {},
            product = {}
        )

        self.__active_instance = _instance

    @property
    def instance(self):
        return self.__active_instance

    def new_instance(self, name=""):

        _instance = self.__active_instance.new()
        print("new_instance")
        self.instances.append( 
            self.__active_instance
        )
        self.__active_instance = _instance

    def switch_instance(self, target):

        ...
        
    
    @staticmethod
    def measure_runtime(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            self.instance.open_instance()
            
            _prod = func(self, *args, **kwargs)

            self.instance.close_instance()
            return _prod
        return wrapper

    

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
            erase_instance: bool = True
        ):

        self.execute(
            method,
            module,
            method_args,
            module_args,
            erase_instance            
        )

    @measure_runtime
    def execute(
            self,
            method: str = None,
            module: str = "single-point",
            method_args: dict[str, Any] | None = None,
            module_args: dict[str, Any] | None = None,
            erase_instance: bool = True
        ):
        ...

    def restart(self,):
        ...

    def store(self):
        raise NotImplementedError
















