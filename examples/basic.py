from ase.build import molecule

import amac
from amac.amac import AMAC

water = molecule("H2O")


amac.set_config("config-amac.json")

calc = AMAC(
    software="deMonNano",
    process_unit=2,
    workdir=".run/",
    label="water",
    execution="inprocess"
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

# ict = calc.set_instance("itc_001", )

calc.run(water) 

calc.new_instance()


calc.run(water) 

print(calc.instance)




