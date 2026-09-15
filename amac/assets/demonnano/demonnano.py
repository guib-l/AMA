
from amac.engine.registry import register_software
from amac.engine.software import FileIOSoftware




@register_software
class deMonNano(FileIOSoftware):

    # Nom du logiciel
    NAME = "DEMON"

    # Autres noms acceptés par le registre
    ALIASES = ("deMonNano",)

    # -----------------------------------------------------
    # Command line

    def command(self, ctx):
        raise NotImplementedError("deMonNano is out of scope for now, see TODO §5")

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



