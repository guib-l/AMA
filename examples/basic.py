from ase.build import molecule

import amac
from amac.amac import AMAC

water = molecule("H2O")


amac.configure_from_file("config-amac.json")

calc = AMAC(
    software="deMonNano",
    process_unit=1,
    workdir=".run/",
    label="water",
    process="inprocess"
)

calc.handler_register("ground-energy")

calc.parameters_register(
    method="dftb-2",
    method_args={
        "basis":{
            "directory":"demon/basis/",
            "ptype":"BIO"
        },
        "scc-max":999,
        "scc-tol":1e-5,
        "filling":50
    },
    module="single-point",
    module_args={}
)

calc.run(water) 
print(calc.instance)

calc.instance.pretty_print()

#calc.new_instance()
#print(calc.instance)


from amac.asset.deMonNano.soft import software_deMonNano

data = dict(
    {"software": {
        "name":"demonNano",
        "process": "inprocess",
        "process_unit": 2,
        "execute": ".",
        "basis": ".",
        "environ": {
            "OMP_NUM_THREADS": 1
        },
        "name": "deMonNano",
        "alias": [
            "demonano",
            "demon_nano",
            "demon-nano"
        ],
        "requires_executable": True
    }})

soft = software_deMonNano(**data["software"])
soft.pretty_print()

