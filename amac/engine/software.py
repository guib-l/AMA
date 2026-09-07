import os
import sys


import amac
from amac.engine.execute import _singleExecute


class Software:

    # Nom du logiciel
    __software__    = "Software"

    # Toutes méthodes accessible avec le logiciel
    __methods__     = []

    # Exetnsion de calcul possible 
    __extension__   = []

    # Module réservée à ce logiciel
    __module__ = []

    # Application réservée à ce logiciel
    __application__ = []

    def __init__(
            self,
            name="",
            workdir=".",
            commands="./",
            execute=_singleExecute,
            shell=True,
            timeout=None):
        
        self.workdir = workdir
        
        self.execute = execute(
            commands,
            workdir,
            shell,
            timeout
        )
        self.name = name

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        if name not in amac._GLOBAL_available_software:
            raise NotImplementedError(
                f"Unknow software {name}. Please select an know one.")
        self._name = name


    def _write_input(self,):
        ...
    
    def _read_output(self,):
        ...

    # Fonction qui est appelé lors de l'exécution
    def resolve(self,):
        ...










