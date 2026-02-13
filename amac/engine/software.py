import os
import sys


import amac
from amac.engine.execute import SimpleExecute


class _base_sofware:

    def __init__(
            self,
            workdir=".",
            commands="./",
            execute=SimpleExecute,
            shell=True,
            timeout=None):
        
        self.workdir = workdir
        
        self.execute = execute(
            commands,
            workdir,
            shell,
            timeout
        )


class software(_base_sofware):

    def __init__(
            self,
            name="",
            **kwargs):

        super().__init__(**kwargs)

        self.name = software
        
    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        if name not in amac._GLOBAL_available_software:
            raise NotImplementedError(
                f"Unknow software {name}. Please select an know one.")
        self._name = name











