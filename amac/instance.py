

import uuid
from typing import *

import copy

from dataclasses import dataclass, field, fields
from amac.context import Context,Result,Explorer,Duration,Properties
from dataclasses import dataclass


@dataclass
class Instance:

    name: str = "default_name"
    id: uuid.UUID = field(default_factory=uuid.uuid4)
    ctx: Context = None
    props: Properties = None
    res: Result = None
    duree: Duration = None
    expl: Explorer = None

    # ------------------------------------------------------------------
    # Representation
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        """
        Human-friendly representation of Instance
        """

        workdir = getattr(self.ctx, "workdir", None)
        complet = getattr(self.res, "complet", None)
        success = getattr(self.res, "success", None)
        duration = getattr(self.duree, "duree", None)

        return (
            f"\n| INSTANCE - {self.id}\n"
            f"|  > name:     {self.name}\n"
            f"|  > workdir:  {workdir}\n"
            f"|  > complet:  {complet}\n"
            f"|  > success:  {success}\n"
            f"|  > duration: {duration} s\n"
        )

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def factory_instance(
        cls,
        name=None,
        image=None,
        # Context
        software=None,
        soft_spec=None,
        execute=None,
        exec_spec=None,
        workdir=None,
        stdout=None,
        stderr=None,
        metadata=None,
        # Result
        return_code=None,
        success=False,
        complet=False,
        errors=None,
        product=None,
        # Explorer
        input_files=None,
        output_files=None,
        annexe_files=None,
        # Properties
        method=None,
        method_attr=None,
        module=None,
        module_attr=None,
        handler=(),
    ):
        """
        Build a new initialized Instance
        """

        if name is None:
            name = "default_name"

        # Normalisation 
        errors = {} if errors is None else errors
        product = {} if product is None else product

        input_files = (
            {} if input_files is None else input_files
        )
        output_files = (
            {} if output_files is None else output_files
        )
        annexe_files = (
            {} if annexe_files is None else annexe_files
        )

        method_attr = (
            {} if method_attr is None else method_attr
        )
        module_attr = (
            {} if module_attr is None else module_attr
        )

        # Properties
        props = Properties(
            image,
            method,
            method_attr,
            module,
            module_attr,
            handler,
        )

        # Exploration of files
        expl = Explorer(
            input_files,
            output_files,
            annexe_files,
        )

        # Context of execution
        ctx = Context(
            software,
            soft_spec,
            execute,
            exec_spec,
            workdir,
            stdout,
            stderr,
            metadata,
        )

        # Duration and time
        duree = Duration(
            date_begin=None,
            date_end=None,
            date_steps=None,
            duree=0.0,
        )

        # Results
        res = Result(
            success,
            complet,
            errors,
            return_code,
            product,
        )

        # Initialization of constructor
        return cls(
            name=name,
            props=props,
            expl=expl,
            ctx=ctx,
            duree=duree,
            res=res,
        )
    
    # ------------------------------------------------------------------
    # Life cycle
    # ------------------------------------------------------------------

    def open_instance(self):
        """Start Instance."""

        if self.duree is None:
            raise RuntimeError(
                "Impossible d'ouvrir l'instance : "
                "la durée n'est pas initialisée."
            )

        return self.duree._open()

    def close_instance(self):
        """Clode Instance"""

        if self.duree is None:
            raise RuntimeError(
                "Impossible de fermer l'instance : "
                "la durée n'est pas initialisée."
            )

        return self.duree._closed()

    # ------------------------------------------------------------------
    # Creat a new Instance
    # ------------------------------------------------------------------
    
    def new_instance(self, name="default_name"):
        """
        Create a new Instance of calculation
        """

        resultat = type(self)(
            name=name,
            ctx=copy.deepcopy(self.ctx),
            props=copy.deepcopy(self.props),
            expl=copy.deepcopy(self.expl),
            res=Result(
                success=False,
                complet=False,
                errors={},
                return_code=None,
                product={},
            ),
            duree=Duration(
                date_begin=None,
                date_end=None,
                date_steps=None,
                duree=0.0,
            ),
        )

        return resultat

    
    # ------------------------------------------------------------------
    # Comparizon
    # ------------------------------------------------------------------

    def __eq__(self, value):
        """
        Compare une instance à :
            - une chaîne : nom ou UUID représenté sous forme de texte ;
            - un UUID ;
            - une autre Instance : comparaison des identifiants.
        """

        if isinstance(value, str):
            return value == self.name or value == str(self.id)

        if isinstance(value, uuid.UUID):
            return self.id == value

        if isinstance(value, Instance):
            return self.id == value.id

        raise TypeError("Object {} isn't a str or Instance object or uuid.UUID object.")

    # ------------------------------------------------------------------
    # Copy
    # ------------------------------------------------------------------

    def __copy__(self):
        """
        Create a simple copy
        """

        cls = type(self)
        resultat = cls.__new__(cls)
        resultat.__dict__.update(self.__dict__)

        return resultat

    def __deepcopy__(self, memo):
        """
        Create a deep-copy
        """

        existing = memo.get(id(self))

        if existing is not None:
            return existing

        cls = type(self)
        resultat = cls.__new__(cls)

        memo[id(self)] = resultat

        for key, value in self.__dict__.items():
            setattr(
                resultat,
                key,
                copy.deepcopy(value, memo),
            )

        return resultat




















