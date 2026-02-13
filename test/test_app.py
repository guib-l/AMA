import os
import sys
import time
from typing import *


from configs import *

from amac.engine.apps import Application
from amac.database.application import single_point


if __name__ == "__main__":



    # - Méthode 1 d'appel
    molecule   = None
    parameters = 'BIO'

    sp = single_point(
        software="deMonNano",
        method="DFTB-2",
        extension=None,
        workdir="./WORKDIR/",
    )
    
    sp.resolve(
        molecule,
        parameters
    )

    print(" > Results : \n",sp.results)
    print("*"*20)

    # - Méthode 2 d'appel
    molecule   = None
    parameters = 'BIO'

    sp = Application(
        application="SP",
        software="deMonNano",
        method="DFTB-2",
        extension=None,
        workdir="./WORKDIR/",
    )
    
    sp.resolve(
        molecule,
        parameters
    )

    print(" > Results : \n",sp.results)
    print("*"*20)


    