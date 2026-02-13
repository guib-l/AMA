import os
import sys
import time

from copy import copy, deepcopy
from typing import Any, Dict, TypeVar, Optional, Type, Union, Callable
from functools import wraps


from configs import *


def mandatory_backend(required_backends: list):
    """Décorateur avec arguments pour valider le type de backend."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(self, *args, **kwargs):
            if not hasattr(self, '_active_backend') or self._active_backend not in required_backends:
                raise RuntimeError(
                    f"Method {func.__name__} requires one of these backends: {required_backends}, "
                    f"but current backend is: {getattr(self, '_active_backend', 'None')}"
                )
            return func(self, *args, **kwargs)
        return wrapper
    return decorator



class BaseType(type):
    """Metaclasse pour valider la présence de méthodes et attributs requis."""

    def __new__(mcls, name: str, bases: tuple, namespace: Dict[str, Any], **kwargs) -> 'BaseType':

        required_methods = namespace.get('REQUIRED_METHODS', [])
        required_attributs = namespace.get('REQUIRED_ATTRIBUTS', [])

        for method in required_methods:
            if method not in namespace:
                raise TypeError(f'Class {name} needs to define method {method}')

        for attr in required_attributs:
            if attr not in namespace:
                raise TypeError(f'Class {name} needs to define attribute {attr}')

        return super().__new__(mcls, name, bases, namespace, **kwargs)


class BaseCheck(metaclass=BaseType):
    """Classe de base pour gérer les backends avec proxy d'attributs."""

    __slots__ = ('required_methods', 'required_attributs')

    _object: Optional[Dict[str, Any]] = None
    _active_object: Optional[Any] = None
    _active_backend: str = ""
    
    #TODO : installer la priorité aux objects locaux ou aux backends
    # "backend" (priorité aux backends) or "local" (priorité aux attributs locaux)
    _priority: str = "backend" 

    def __getattr__(self, name):
        #print(f"     __getattr__ called for: {name}")
        bound_name = self.__bind__(name)
        
        if self._active_object and hasattr(self._active_object, bound_name):
            return getattr(self._active_object, bound_name)
        
        if hasattr(self, bound_name):
            return getattr(self, bound_name)
        
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute '{name}'")

    def __getattribute__(self, name):
        #print(f"__getattribute__ called for: {name}")
        return super().__getattribute__(name)

    def __setattr__(self, name, value):
        #print(f"     __setattr__ called for: {name}")
        if name.startswith('_'):
            object.__setattr__(self, name, value)
            return
            
        bound_name = self.__bind__(name)
        
        if bound_name not in self.__dict__:
            object.__setattr__(self, bound_name, value)
        else:
            if (hasattr(self, '_active_object') and 
                    self._active_object and 
                    not hasattr(self, bound_name)):
                setattr(self._active_object, bound_name, value)
            else:
                object.__setattr__(self, bound_name, value)

    def __bind__(self, attr_name: str) -> str:
        if attr_name.startswith('_'):
            return attr_name
        
        if not self._active_backend or not self._object:
            return attr_name
        
        backend_config = self._object.get(self._active_backend, {})
        binding = backend_config.get('binding')
        
        if binding and isinstance(binding, dict) and attr_name in binding:
            return binding[attr_name]
        
        return attr_name

    def __check__(self):
        """Vérifie que le backend actif possède les méthodes et attributs requis."""
        if not hasattr(self, '_active_backend') or not self._active_backend:
            raise RuntimeError("No active backend object to check.")
        

class Backend(BaseCheck):

    REQUIRED_METHODS   = ()
    REQUIRED_ATTRIBUTS = ()


    def __init_subclass__(cls, **kwargs):
        cls._object = kwargs.get('binding', None)
        

    def __init__(self, 
                 backend="",
                 priority="backend",
                 **kwargs):
        
        self._active_backend = backend
        self._priority = priority
        
        for key in self._object.keys():
            self.__partial_init__(key, **kwargs)
        
        self.__switch__(backend)

    def __partial_init__(self, _obj: str, **kwargs) -> None:

        if _obj not in self._object:
            raise ValueError(f"Backend '{_obj}' not found in object pool")
            
        backend_config = self._object[_obj]
        required_keys = ['object', 'attributes']
        
        for key in required_keys:
            if key not in backend_config:
                raise ValueError(f"Backend '{_obj}' missing required key: {key}")
        
        attributes = backend_config['attributes']
        if not isinstance(attributes, (list, tuple)):
            raise ValueError(f"Backend '{_obj}' attributes must be a list or tuple")
        
        data = {
            key: kwargs.get(key, None) for key in attributes
        }
        
        try:
            self._object[_obj]['object'] = backend_config['object'](**data)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize backend '{_obj}': {e}")
           
        
    def __switch__(self, _obj) -> None:

        self.__check__()

        if _obj not in self._object:
            available = ', '.join(self._object.keys())
            raise ValueError(f'Backend "{_obj}" not found. Available backends: {available}')
        
        if 'object' not in self._object[_obj]:
            raise ValueError(f'Backend "{_obj}" is missing required "object" key')
            
        self._active_backend = _obj
        self._active_object = self._object[_obj]['object']

    def __backend_error__(self, func_name: str, error: Exception) -> None:
        raise RuntimeError(
            f"Error in backend '{self._active_backend}' during '{func_name}': {error}"
        )
        
    def switch_backend(self, backend: str) -> None:
        """Change le backend actif."""
        self.__switch__(backend)

