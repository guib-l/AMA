import os
import sys
import time
from copy import copy, deepcopy
from typing import Any, Dict, TypeVar, Optional, Type, Union, Callable
from functools import wraps
from configs import *

from ama.calculator.backend import Backend, mandatory_backend




class A:
    def __init__(self, value=None):
        self.value = value
        
    def a(self,):
        return 5.00
    
    def b(self,):
        return 15.00
    

class B:
    def __init__(self, data=None):
        self.data = data
        
    def a(self,**kwargs):
        return 3.00
    
    def c(self,):
        return 9.00

_bind = {
    'object_A':{
        'object':A,
        'attributes':['value'],
        'binding':{
            'value': 'data'
            },
        }, 
    'object_B':{
        'object':B,
        'attributes':['data'],
        'binding':{
            'b': 'd',
            },
        }
    }


class Atoms(Backend, binding=_bind):
    """Classe principale pour gérer les atomes avec différents backends."""

    def __init__(self, 
                 data: Optional[Any] = None, 
                 **backend) -> None:

        super().__init__(**backend)
        self.data = data
        
    def a(self, value=1.00) -> float:
        """Méthode a avec validation et logging."""
        return 1.00 * value
    
    def d(self) -> float:
        """Méthode d avec validation et logging."""
        return 4.00
    
    @mandatory_backend(['object_B',])
    def method_with_backend_restriction(self) -> str:
        """Exemple de méthode qui ne fonctionne qu'avec certains backends."""
        return f"Method called with backend: {self._active_backend}"
    


if __name__ == "__main__":

    data = {"dat":1, }

    atoms = Atoms(data=data, 
                  backend='object_A', )
    
    print(f">>> Active backend: {atoms._active_backend}")
    #print(f"Active object:  {atoms._active_object}")


    result_a = atoms.a(value=2.00)
    print(f"Result a: {result_a}")

    result_b = atoms.b()
    print(f"Result b: {result_b}")

    atoms.switch_backend('object_B')
    print(f">>> Active backend: {atoms._active_backend}")

    result_d = atoms.d()
    print(f"Result d: {result_d}")

    # Test du décorateur avec arguments
    result_restricted = atoms.method_with_backend_restriction()
    print(f"Result restricted method: {result_restricted}")

    sys.exit()











