
import os
import json

__version__ = "0.1.1"


# Global configuration defaults
_GLOBAL_available_executable = {
    "ORCA_EXECUTABLE" : None,
    "DEMON_EXECUTABLE" : None,
    "DFTBP_EXECUTABLE" : None,
    "GAUSSIAN_EXECUTABLE" : None,
}


_GLOBAL_available_software = {
    'deMonNano':"DEMON",
    'DFTB+':"DFTBP",
    'Orca':"ORCA",
    'Gaussian':"GAUSSIAN",
}

_GLOBAL_available_methods = [
    "DFTB", 
    "DFTB-2", 
    "DFTB-3",
    "GNF1-xTB", 
    "GNF2-xTB",
    "HF",
    "DFT",
    "delta-DFT",
    "DFT-CI",
    "MP2",
    "MRCI",
    "CCSD",
    "CCSDT",
    "CAS",
    "CASPT2"
]

_GLOBAL_available_module = []


_GLOBAL_available_application = []




def configure(name=None, executable=None):
    """Set global default values for executable and basis.

    Args:
        executable: Path to the deMonNano executable.
        basis: Basis configuration dictionary.
    """    
    if name is not None and name in _GLOBAL_available_software.items()[1]:
        _GLOBAL_available_executable[f"{name}_EXECUTABLE"] = executable




