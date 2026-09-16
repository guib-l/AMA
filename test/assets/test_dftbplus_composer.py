"""Tests of the DFTB+ composer: geometry block, injected options and units."""

import pytest
from ase.build import bulk, molecule

from amac.assets.dftbplus.composer import DftbPlusComposer, geometry_block
from amac.assets.dftbplus.dftbplus import DftbPlus
from amac.parameter.parameters import CalculationSpec, ExecutionSpec
from amac.parameter.schema import load

INPUT_FILE = "dftb_in.hsd"


@pytest.fixture
def schema():
    return load(DftbPlus.DOC)


def make_spec(**overrides) -> CalculationSpec:
    kwargs = {
        "method": "TIGHT_BINDING",
        "method_args": {
            "variant": "DFTB2",
            "MaxAngularMomentum": {"O": "p", "H": "s"},
        },
        "parameters": {
            "SLATER_KOSTER_FILES": {"variant": "Type2FileNames", "Prefix": "mio"}
        },
    }
    return CalculationSpec.from_kwargs(**kwargs | overrides)


def compose(schema, spec, atoms=None, exec_spec=None) -> str:
    files = DftbPlusComposer().compose(
        spec, schema, atoms, exec_spec or ExecutionSpec()
    )
    assert list(files) == [INPUT_FILE]
    return files[INPUT_FILE]


def test_geometry_block_of_a_molecule():
    text = geometry_block(molecule("H2O"))
    lines = text.splitlines()
    assert lines[0] == "Geometry = GenFormat {"
    assert lines[1].split() == ["3", "C"]
    assert lines[2].split() == ["O", "H"]
    assert lines[-1] == "}"
    assert all(line == line.rstrip() for line in lines)


def test_geometry_block_of_a_crystal_holds_the_lattice():
    text = geometry_block(bulk("Si", "diamond", a=5.43, cubic=True))
    lines = [line for line in text.splitlines() if line.strip()]
    assert lines[1].split() == ["8", "S"]
    # One origin line and three lattice vectors after the eight atoms.
    assert [word for word in lines[-2].split()] == ["0.000000000000000"] * 2 + [
        "5.430000000000000"
    ]
    # Opening line, the two gen header lines, 8 atoms, origin and 3 vectors, "}".
    assert len(lines) == 1 + 2 + 8 + 4 + 1


def test_compose_writes_the_geometry_then_the_tree(schema):
    text = compose(schema, make_spec(), molecule("H2O"))
    assert text.startswith("Geometry = GenFormat {")
    assert "Hamiltonian = DFTB {" in text
    assert "SCC = Yes" in text  # SETS of the DFTB2 variant.
    assert text.index("Geometry") < text.index("Hamiltonian")


def test_write_results_tag_is_injected(schema):
    text = compose(schema, make_spec(), molecule("H2O"))
    assert "Options = {\n  WriteResultsTag = Yes\n}" in text


def test_write_results_tag_of_the_user_is_kept(schema):
    parameters = {
        "SLATER_KOSTER_FILES": {"variant": "Type2FileNames", "Prefix": "mio"},
        "OPTIONS": {"WriteResultsTag": False},
    }
    text = compose(schema, make_spec(parameters=parameters), molecule("H2O"))
    assert "WriteResultsTag = No" in text
    assert "WriteResultsTag = Yes" not in text


def test_gradient_module_injects_print_forces(schema):
    text = compose(schema, make_spec(module="GRADIENT"), molecule("H2O"))
    assert "Analysis = {\n  Printforces = Yes\n}" in text
    assert "Driver = {}" in text


def test_single_point_does_not_inject_print_forces(schema):
    text = compose(schema, make_spec(module="SINGLE_POINT"), molecule("H2O"))
    assert "Printforces" not in text


def test_units_are_written_with_the_dftbplus_names(schema):
    parameters = {
        "SLATER_KOSTER_FILES": {"variant": "Type2FileNames", "Prefix": "mio"},
        "FILLING": {"Fermi": {"Temperature": 0.001}},
    }
    text = compose(schema, make_spec(parameters=parameters), molecule("H2O"))
    assert "Temperature [Hartree] = 0.001" in text


def test_cpu_stays_out_of_the_input(schema):
    """DFTB+ takes its core count from OMP_NUM_THREADS, not from its input.

    The ``doc.json`` therefore declares no ``INPUT.RESOURCES``: ``Parallel {
    Groups }`` counts MPI process groups, not cores.
    """
    text = compose(schema, make_spec(), molecule("H2O"), ExecutionSpec(cpu=4))
    assert "Parallel" not in text
    assert "Groups" not in text


def test_raw_geometry_replaces_the_atoms(schema):
    spec = make_spec(raw={"Geometry": {"xyzFormat": "geo.xyz"}})
    text = compose(schema, spec, molecule("H2O"))
    assert "GenFormat" not in text
    assert "xyzFormat = geo.xyz" in text
    assert "0.763239" not in text  # No position of the ase.Atoms was written.


def test_compose_without_geometry_fails(schema):
    with pytest.raises(ValueError, match="needs a geometry"):
        compose(schema, make_spec(), None)
