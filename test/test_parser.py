import os
import sys
import time
from typing import *


from configs import *

from amac.ios.parser import Parser
from amac.ios.molden import read_XYZ,write_XYZ


import ase
from ase.visualize import view


if __name__ == "__main__":


    DIR = "../data"
    SRC = "reduced_data_naf5.xyz"
    filename = os.path.join(DIR,SRC)

    data = read_XYZ(filename=filename, is_charges=False)
    

    DIR = "../data"
    SRC = "first_naf5.xyz"
    filename = os.path.join(DIR,SRC)

    write_XYZ(filename=filename, images=data[0][:3])

    view(data[0])
















