
from amac.engine.software import Software




class dftbplus(Software):

    # Nom du logiciel
    __software__    = "dftb+"

    # Toutes méthodes accessible avec le logiciel
    __methods__     = ["DFTB","SCC-DFTB","DFTB3"]

    # Exetnsion de calcul possible 
    __extension__   = ["TD","DISP"]

    # Modules réservée à ce logiciel
    __module__ = ["OPT","MD"]

    # Appication attendue
    __application__ = ["energies","forces","mulliken_charges",
                       "dipole","eigenvalues"]


    def __init__(self, **parameters):

        Software.__init__(self, )


    # -----------------------------------------------------
    # Reading/Writing 

    def _write_input(self,):
        ...
    
    def _read_output(self,):
        ...

    # -----------------------------------------------------
    # Resolved calculation

    def resolve(self,):
        ...

    # -----------------------------------------------------
    # Application

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



