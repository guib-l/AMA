import os
import sys
import time
from typing import *


from configs import *

from ama.ios.utils import progressbar
from ama.ios.parser import Parser
from ama.ios.molden import read_XYZ,write_XYZ

from ama.analyse.geometry import *


import ase
from ase.visualize import view



if __name__ == "__main__":

    # =========================================================================

    DIR = "../data"
    SRC = "reduced_data_naf5.xyz"
    filename = os.path.join(DIR,SRC)

    data = read_XYZ(filename=filename, is_charges=False)
    
    images  = data[0]
    comment = data[1]

    energies = list(map(lambda x: float(x.split()[4]),comment, ))

    Nimg = len(images)
    image = images[0]

    acceptable = []

    for it in progressbar(range(Nimg), "Computing: ", 40):
            
        frags = define_fragments(images[it], [18,]*5)
        dist = distances_com(frags)

        acceptable.append(
            check_distances_fragments(dist,
                trigger_max=10.0,
                strict_trigger_max=20.0,
                trigger_min=2.0 
            )
        )

    accept_images = [img for i,img in enumerate(images) if acceptable[i]]
    accept_energy = [e for i,e in enumerate(energies) if acceptable[i]]

    DIR = "../data"
    SRC = "compact_naf5.xyz"
    filename = os.path.join(DIR,SRC)

    write_XYZ(filename=filename, images=accept_images)


    # =========================================================================







    
