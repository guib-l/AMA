
from amac.engine.software import software




class deMonNano(software):

    # Nom du logiciel
    __software__    = "deMonNano"

    # Toutes méthodes accessible avec le logiciel
    __methods__     = ["DFTB","DFTB-2",]

    # Exetnsion de calcul possible 
    __extension__   = ["TD","D3","QM/MM","WMULL","CM3"]

    # Application réservée à ce logiciel
    __application__ = ["OPT","MD","PTMC","PTMD"]

    def __init__(self):
        pass








