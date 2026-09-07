import os
import sys
import time

from ase import Atoms

from amac.amac import AMAC
from amac.assets import orca


if __name__ == "__main__":

    # ========================================
    # Ce a quoi je souhaite que cela ressemble

    image = Atoms(
        ["O", "H", "H", "O", "H", "H"],
        positions=np.array(
            [
                [1.2478, -0.5185, 3.4049],
                [1.5946, -1.4204, 3.3886],
                [0.9008, -0.3341, 2.5062],
                [3.2478, -0.4185, 3.4049],
                [3.5946, -1.5204, 3.3886],
                [2.9008, -0.3341, 2.6062],
            ]
        ),
    )

    # Paramètres du calcul demandé
    calculation_parameters = {
        "method_args":{     
            "xc":"PBE0",
            "basis":"cc-PVDZ",
        },
        "module_args":{},
    }

    calculation_argument = {
        "cpu":2,
        "ram":4000,
        "workdir":"/scratch/basis-calc/",
        "outdir":None,
        "run-delay":None,           # Delay avant démarage du calcul
        "stop-delay":None,          # Delay aprèss lequel le calcul coupe
    }

    # Appel du calculateur AMAC (généraliste)
    calc = AMAC(
        backend="ORCA",             # Le software utilisé
        method="DFT",               # Method de calcul
        module=None,                # Module du calcul
        **calculation_argument,     # paramètres de l'éxécution du calcul
        **calculation_parameters    # Paramètres du calcul 
    )

    # Handler de récupération des résultats
    # (possibilité de doner un handler custom)
    calc.handler_properties(
        orca.energies,              # Récupérartion des énergies
        orca.forces,                # Récupération des forces
        orca.dipole,
        orca.eigenvalues
    )

    calc.execute(
        geometry=image,             # Géométrie sur lequel s'applique le calcul
        pbc=False,
    )

    calc.store(
        filename="store-dft-orca",
        format="json",
    )









    sys.exit()

