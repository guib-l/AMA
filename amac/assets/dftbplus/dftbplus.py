
from pathlib import Path

from amac.engine.registry import register_software
from amac.engine.software import FileIOSoftware




@register_software
class dftbplus(FileIOSoftware):

    # Nom du logiciel
    NAME = "DFTBP"

    # Autres noms acceptés par le registre
    ALIASES = ("DFTB+",)

    # Description déclarative du logiciel
    DOC = Path(__file__).with_name("doc.json")

    # -----------------------------------------------------
    # Command line

    def command(self, ctx):
        raise NotImplementedError("DFTB+ is out of scope for now, see TODO §5")

    # ---------------------------------------------------------------
    # Available handler

    def energies(self,):
        pass

    def mulliken_charges(self,):
        pass

    def dipole(self,):
        pass

    def eigenvalues(self,):
        pass

    def forces(self,):
        pass



