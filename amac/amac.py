
import sys
import uuid
import copy
from pathlib import Path
from typing import *

import ase

import time
from functools import wraps
from amac.asset import resolved_software

from amac.context import Context,Result,Explorer,Duration,Properties
from amac.instance import Instance
from dataclasses import dataclass




class AMAC:

    label: str = "AMAC.calculator"
    instances: List[Instance] = []
    __active_instance: Instance | None = None

    def __init__(
            self,
            *,
            software: str | None = None,
            process_unit: int = 1,
            workdir: str | Path = '.',
            label: str | None = "AMAC.calculator",
            process: str | None = "inprocess",
            config_spec: dict = {},
            stdout = sys.stdout,
            stderr = sys.stderr,
        ):
        self.label = label

        self._soft = resolved_software(
            software,
            process=process,
            process_unit=process_unit,
        )

        #_instance = Instance.factory_instance(
        #    software = self._soft,
        #    soft_spec = config_spec,
        #    workdir = workdir,
        #)
        #self.__active_instance = _instance


    @property
    def instance(self):
        return self.__active_instance

    #def new_instance(self, name=""):
    #    _instance = self.__active_instance.new_instance()
    #    
    #    self.instances.append( 
    #        self.__active_instance
    #    )
    #    self.__active_instance = _instance
    

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

    @staticmethod
    def new_instance(func):
        @wraps(func)
        def wrapper(self, *args, **kwargs):

            if self.__active_instance is not None:
                self.instances.append(
                    copy.deepcopy(self.__active_instance)
                )

                _instance = Instance.factory_instance(
                    **self.instance.props.to_dict(),
                    **self.instance.ctx.to_dict()
                )
            else:
                _instance = Instance.new_instance()
            self.__active_instance = _instance


            _prod = func(self, *args, **kwargs)

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

    @new_instance
    def parameters_register(
            self, 
            image = None,
            method = None,
            module = None,
            method_args = None,
            module_args = None,
        ):

        self.__active_instance.properties(
            image=image,
            method=method,
            module=module,
            method_args=method_args,
            module_args=module_args, 
        )
    
    def run(
            self,
            image: ase.Atoms = None,
            erase_instance: bool = True
        ):
        
        self.execute(
            image=image
        )

    @measure_runtime
    def execute(
            self,
            **kwargs
        ):
        self.__active_instance.props(**kwargs)


        self.__active_instance.res.complet = True

    def restart(self,):
        ...

    def store(self):
        raise NotImplementedError
















