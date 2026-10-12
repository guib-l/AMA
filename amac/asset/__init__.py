



from amac.asset.deMonNano.soft import software_deMonNano
from amac.asset.dftbplus.soft import software_dftbplus


available_software = [
    software_deMonNano,
    software_dftbplus
]

def resolved_name(_soft, _name:str) -> bool:
    """ """
    if _name==_soft.name:
        return True
    if _name in _soft.alias:
        return True
    return False

def resolved_software(_name:str, **config):

    if _name is None:
        raise NotImplementedError(f"Software (None) is unknkow")

    for soft in available_software:
        if resolved_name(soft, _name):
            return soft(**config)
    
    raise NotImplementedError(f"Software {_name} is unknkow")















