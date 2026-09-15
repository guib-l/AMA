
from amac.engine.registry import register_software
from amac.engine.software import FileIOSoftware




@register_software
class Orca(FileIOSoftware):

    # Nom du logiciel
    NAME = "ORCA"

    # Autres noms acceptés par le registre
    ALIASES = ()

    # ---------------------------------------------------------------
    # Command line

    def command(self, ctx):
        raise NotImplementedError("ORCA is out of scope for now, see TODO §5")

    # ---------------------------------------------------------------
    # Available handler

    def energies(self,):
        pass

    def mulliken_charges(self,):
        pass

    def dipole(self,):
        pass

    def forces(self,):
        pass


