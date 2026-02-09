import os
import sys
import time




if __name__ == "__main__":

    # ========================================
    # Ce a quoi je souhaite que cela ressemble

    

    # Appel du calculateur AMAC (généraliste)
    calc = AMAC(
        method="DFT",          # La méthode qui est demandé
        calcul="single-point"  # Type de calcul demandé
        backend="ORCA",        # Le software utilisé
        base="cc-PVDZ",      
        xc="PBE",
    )

    # Handler de récupération des résultats
    # (possibilité de doner un handler custom)
    calc.handler_properties(
        orca.energies,         # Récupérartion des énergies
        orca.forces,           # Récupération des forces
    )

    calc.execute(
        geometry=image,        # Géométrie sur lequel s'applique le calcul
    )











    sys.exit()

