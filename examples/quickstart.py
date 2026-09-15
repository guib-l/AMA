"""Quickstart: run the dummy test software with the AMAC class and with the facade.

Usage::

    python examples/quickstart.py [WORKDIR]

Without ``WORKDIR``, everything is written in a temporary directory removed at the
end. The dummy software needs no external program: its fake calculation runs with
the current Python interpreter.
"""

import sys
import tempfile
from pathlib import Path

import numpy as np
from ase import Atoms

try:
    import amac
except ModuleNotFoundError:
    # AMAC is not packaged yet: make the root of the repository importable.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import amac

from amac import AMAC
from amac.assets import _dummy


def water_dimer() -> Atoms:
    """Return a water dimer."""
    positions = np.array(
        [
            [1.2478, -0.5185, 3.4049],
            [1.5946, -1.4204, 3.3886],
            [0.9008, -0.3341, 2.5062],
            [3.2478, -0.4185, 3.4049],
            [3.5946, -1.5204, 3.3886],
            [2.9008, -0.3341, 2.6062],
        ]
    )
    return Atoms(["O", "H", "H", "O", "H", "H"], positions=positions)


def atom_count(ctx) -> int:
    """Custom handler: any callable receiving the run context."""
    return len(ctx.atoms)


def run_with_class(workdir: Path) -> None:
    """Explicit calculator: validate, run, extract, store and reload."""
    calc = AMAC(
        software="dummy",
        method="DFT",
        method_args={"variant": "B3LYP"},
        module=None,
        parameters={"BASIS": "cc-pVDZ", "SCF": {"MaxIter": 200}},
        cpu=2,
        ram=4000,
        workdir=workdir,
        label="water-dimer",
        overwrite=True,
    )
    calc.handler_properties(_dummy.energy, _dummy.forces, atom_count)
    result = calc.execute(water_dimer())
    print(f"[AMAC] success={result.success} properties={result.properties}")

    path = calc.store(workdir / "store-dft-dummy")
    [reloaded] = amac.load(path)
    provenance = reloaded.provenance
    print(
        f"[AMAC] reloaded {path.name}: energy={reloaded.properties['energy']} "
        f"software={provenance['software']} duration={provenance['duration']:.3f} s"
    )


def run_with_facade(workdir: Path) -> None:
    """Facade: configured defaults, a current calculator and several images."""
    amac.configure(cpu=2, workdir=workdir, overwrite=True)
    amac.calculator(
        parameters={
            "method": "DFT",
            "method_args": {"variant": "PBE"},
            "parameters": {"BASIS": "sto-3g"},
        },
        platform="dummy",
        label="facade",
        handlers=[_dummy.energy, atom_count],
    )
    for result in amac.run([water_dimer(), water_dimer()]):
        print(
            f"[facade] {result.context.directory.name}: success={result.success} "
            f"properties={result.properties}"
        )


def main(argv: list[str]) -> None:
    """Run both variants in ``argv[1]``, or in a temporary directory."""
    if len(argv) > 1:
        workdir = Path(argv[1])
        workdir.mkdir(parents=True, exist_ok=True)
        run_with_class(workdir)
        run_with_facade(workdir)
        return
    with tempfile.TemporaryDirectory(prefix="amac-quickstart-") as directory:
        run_with_class(Path(directory))
        run_with_facade(Path(directory))


if __name__ == "__main__":
    main(sys.argv)
