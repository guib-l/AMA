
from amac.engine.software import Software




class Orca(Software):

    # Nom du logiciel
    __software__    = "Orca"

    # Toutes méthodes accessible avec le logiciel
    __methods__     = ["DFT","MP2"]

    # Exetnsion de calcul possible 
    __extension__   = ["DISP",]

    # Modules réservée à ce logiciel
    __module__ = []

    __application__ = ["energies","forces","mulliken_charges",]


    def __init__(self):
        pass

    def energies(self,):
        pass

    def mulliken_charges(self,):
        pass

    def dipole(self,):
        pass

    def forces(self,):
        pass


