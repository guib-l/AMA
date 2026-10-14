

import uuid
from typing import *

import copy

from amac.context import Context,Result,Explorer,Duration,Properties
from dataclasses import dataclass


@dataclass
class Instance:

    name: str = "default_name"
    id: uuid.UUID = uuid.uuid4()
    ctx: Context = None
    props: Properties = None
    res: Result = None
    duree: Duration = None
    expl: Explorer = None

    def __repr__(self):
        repr = f"\n| INSTANCE - {self.id}\n|  > name: {self.name}\n"
        repr += f"|  > workdir:  {self.ctx.workdir}\n"
        repr += f"|  > complet:  {self.res.complet}\n"
        repr += f"|  > success:  {self.res.success}\n"
        repr += f"|  > duration: {self.duree.duree} s\n"
        return repr

    @classmethod
    def new_instance(
            cls, 
            name = None, 
            image = None,
            # Context
            software = None,
            soft_spec = None,
            execute = None,
            exec_spec = None,
            workdir = None,
            stdout = None,
            stderr = None,
            metadata = None,
            # Result
            return_code = None,
            success = False,
            complet = False,
            errors = {},
            product = {},
            # Explorer
            input_files = {},
            output_files = {},
            annexe_files = {},
            # Properties
            method = None,
            method_attr = {},
            module = None,
            module_attr = {},
            handler = (),
        ):
        if name is None:
            name = "default_name"

        props = Properties(
            image, method, method_attr,
            module, module_attr, handler           
        )

        expl = Explorer(
            input_files,
            output_files,
            annexe_files            
        )

        ctx=Context(
            software, soft_spec, execute,
            exec_spec, workdir, stdout,
            stderr, metadata,    
        )

        duree = Duration(
            date_begin=None,
            date_end=None,
            date_steps=None,
            duree=0.0
        )

        res = Result(
            success,
            complet,
            errors,
            return_code,
            product
        )
        return cls(name=name, props=props, expl=expl, ctx=ctx, duree=duree, res=res)
    
    def open_instance(self):
        self.duree._open()

    def close_instance(self):
        self.duree._closed()


    def new(self, name="default_name"):
        cls = type(self)
        resultat = cls.__new__(cls)
        print(resultat)
        _authorized = ["ctx","props"]
        for key, value in self.__dict__.items():
            if key in _authorized:
                setattr(resultat, key, copy.deepcopy(value))
        resultat.name = name
        print(resultat)
        return resultat

    def __eq__(self, value):
        if isinstance(value,str):
            if value == self.name:
                return True
            elif value == self.id:
                return True
            else:
                return False
        if isinstance(value,uuid.UUID):
            if value == self.id:
                return True
            else:
                return False
        if isinstance(value,Instance):
            return self.__eq__(value.id)
        raise TypeError("Object {} isn't a str or Instance object or uuid.UUID object.")

    def __copy__(self):
        cls = type(self)
        resultat = cls.__new__(cls)
        resultat.__dict__.update(self.__dict__)
        return resultat

    def __deepcopy__(self, memo):
        cls = type(self)
        resultat = cls.__new__(cls)
        memo[id(self)] = resultat

        for cle, valeur in self.__dict__.items():
            setattr(resultat, cle, copy.deepcopy(valeur, memo))

        return resultat



















