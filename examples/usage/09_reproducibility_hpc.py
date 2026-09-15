"""Save a calculation as JSON on a cluster node and run it again elsewhere.

Illustrative: requires the real software, their handlers and composers, not
implemented yet.

``to_dict()`` keeps the spec, the execution settings (``env`` values masked), the
software, the validation mode, the requested driver and the importable handlers.
``AMAC.from_dict`` imports these handlers again: only load files you trust. Settings
that depend on the machine (``workdir``, ``executable``, ``cpu``, ``env``...) are
overridden for one call in ``execute()``.
"""

import json
from pathlib import Path

from ase.build import molecule

import amac
from amac import AMAC
from amac.assets import gaussian

SPEC_FILE = Path("benzene-opt.amac.json")


def prepare_on_cluster() -> None:
    """Describe a long Gaussian optimisation and save it."""
    calc = AMAC(
        software="GAUSSIAN",
        method="DFT",
        method_args={"variant": "wB97X-D"},
        module="OPT",
        parameters={"BASIS": "6-311+G(d,p)"},
        cpu=32,
        ram=64000,  # Mo
        timeout=12 * 3600,  # s, tue tout le groupe de processus au-delà
        workdir="/scratch/amac",
        outdir=Path.home() / "results",  # copie de chaque répertoire de calcul
        keep_files=False,  # répertoire de travail supprimé après les handlers
        env={"GAUSS_SCRDIR": "/scratch/g16"},
        label="benzene-opt",
        overwrite=True,
    )
    calc.handler_properties(gaussian.energy, gaussian.final_geometry)
    # Valeurs d'env masquées par défaut ; handlers stockés en "module:qualname".
    SPEC_FILE.write_text(json.dumps(calc.to_dict(), indent=4), encoding="utf-8")


def run_elsewhere() -> None:
    """Rebuild the calculation on a workstation and run it with local settings."""
    data = json.loads(SPEC_FILE.read_text(encoding="utf-8"))
    calc = AMAC.from_dict(data)  # avertit : GAUSS_SCRDIR masquée, à repasser
    print([meta.name for meta in calc.handlers])  # ['energy', 'final_geometry']

    workdir = Path.home() / "amac-runs" / "09-rerun"
    result = calc.execute(
        molecule("C6H6"),
        workdir=workdir,
        outdir=None,
        keep_files=True,
        executable="/usr/local/g16/g16",
        cpu=8,
        ram=16000,
        env={"GAUSS_SCRDIR": "/tmp/g16"},
    )
    path = calc.store(Path.home() / "amac-runs" / "benzene-opt")
    [reloaded] = amac.load(path)
    provenance = reloaded.provenance
    print(f"{provenance['software']} on {provenance['hostname']}")
    print(f"cpu={provenance['exec_spec']['cpu']} env={provenance['exec_spec']['env']}")
    print(f"energy={result.properties['energy']:.8f} Eh")

    # Dipôle oublié : relu dans les fichiers conservés, sans relancer Gaussian.
    dipole = calc.reprocess(result.context.directory, handlers=[gaussian.dipole])
    print(f"dipole={dipole.properties['dipole']}")


def main() -> None:
    """Both steps; on real machines they run on two different hosts."""
    prepare_on_cluster()
    run_elsewhere()


if __name__ == "__main__":
    main()
