
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

    def input_composer(self, user_values):
        # TODO : composer l'input de deMonNano à partir des user_values
        return "Input data for deMonNano"
    
    def output_parser(self, output_data):
        # TODO : parser les résultats de deMonNano à partir de output_data
        return {"energy": 99999.9999, "geometry": "optimized geometry data"}







