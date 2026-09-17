"""Tests of the ORCA composer: keyword line, blocks, resources and geometry."""

import pytest
from ase.build import bulk, molecule

from amac.assets.orca.composer import OrcaComposer, geometry_block
from amac.assets.orca.orca import Orca
from amac.parameter.parameters import CalculationSpec, ExecutionSpec
from amac.parameter.schema import load
from amac.parameter.validator import validate

INPUT_FILE = "orca.inp"
WATER = object()  # Default of the compose() helper, distinct from "no geometry".


@pytest.fixture
def schema():
    return load(Orca.DOC)


def make_spec(**overrides) -> CalculationSpec:
    kwargs = {
        "method": "DFT",
        "method_args": {"variant": "PBE0"},
        "module": "SINGLE_POINT",
        "parameters": {"BASIS": "def2-SVP"},
    }
    return CalculationSpec.from_kwargs(**kwargs | overrides)


def compose(schema, spec, atoms=WATER, exec_spec=None) -> str:
    files = OrcaComposer().compose(
        spec,
        schema,
        molecule("H2O") if atoms is WATER else atoms,
        exec_spec or ExecutionSpec(),
    )
    assert list(files) == [INPUT_FILE]
    return files[INPUT_FILE]


def test_keyword_line_holds_the_variant_the_module_and_the_basis(schema):
    text = compose(schema, make_spec())
    assert text.splitlines()[0] == "! PBE0 SP def2-SVP"


def test_geometry_block_closes_the_file(schema):
    text = compose(schema, make_spec(), molecule("H2O"))
    lines = text.splitlines()
    assert lines[-5] == "* xyz 0 1"
    assert lines[-1] == "*"
    assert [line.split()[0] for line in lines[-4:-1]] == ["O", "H", "H"]


def test_charge_and_multiplicity_come_from_the_parameters(schema):
    spec = make_spec(parameters={"BASIS": "def2-SVP", "CHARGE": 1, "MULTIPLICITY": 2})
    text = compose(schema, spec)
    assert "* xyz 1 2" in text
    # They are written on the geometry line only, never as a block.
    assert "*xyz" not in text
    assert "Multiplicity" not in text


def test_geometry_block_of_a_molecule():
    text = geometry_block(molecule("H2O"), 0, 1)
    lines = text.splitlines()
    assert lines[0] == "* xyz 0 1"
    assert len(lines) == 5
    assert all(line == line.rstrip() for line in lines)


def test_maxcore_is_the_memory_per_core(schema):
    text = compose(schema, make_spec(), exec_spec=ExecutionSpec(cpu=4, ram=8000))
    assert "%pal\n  nprocs 4\nend" in text
    assert "%maxcore 2000" in text


def test_maxcore_without_ram_is_not_written(schema):
    text = compose(schema, make_spec(), exec_spec=ExecutionSpec(cpu=2))
    assert "%maxcore" not in text
    assert "nprocs 2" in text


def test_solvation_renders_the_cpcm_block(schema):
    parameters = {
        "BASIS": "def2-SVP",
        "SOLVATION": {"variant": "SMD", "SMDsolvent": "water"},
    }
    text = compose(schema, make_spec(parameters=parameters))
    # The given value comes first, the one imposed by SETS after it.
    assert "%cpcm\n  SMDsolvent water\n  SMD true\nend" in text


def test_excited_states_render_the_tddft_block(schema):
    parameters = {
        "BASIS": "def2-SVP",
        "EXCITED_STATES": {"variant": "LR-TDDFT", "NRoots": 5},
    }
    text = compose(schema, make_spec(parameters=parameters))
    assert "%tddft\n  NRoots 5\n  TDA false\nend" in text


def test_dispersion_and_approximation_join_the_keyword_line(schema):
    parameters = {
        "BASIS": "def2-SVP",
        "DISPERSION": "D3BJ",
        "INTEGRAL_APPROXIMATION": "RIJCOSX",
        "AUXILIARY_BASIS": "def2/J",
    }
    text = compose(schema, make_spec(parameters=parameters))
    # The inline nodes follow the order of the parameters, after the keywords.
    assert text.splitlines()[0] == "! PBE0 SP def2-SVP D3BJ RIJCOSX def2/J"


def test_module_keyword_of_a_gradient(schema):
    text = compose(schema, make_spec(module="GRADIENT"))
    assert text.splitlines()[0] == "! PBE0 EnGrad def2-SVP"


def test_raw_lines_follow_the_keyword_line(schema):
    spec = make_spec(raw=["%output", "  Print[P_Hirshfeld] 1", "end"])
    lines = compose(schema, spec).splitlines()
    assert lines[1:4] == ["%output", "  Print[P_Hirshfeld] 1", "end"]


def test_raw_cannot_redefine_the_geometry(schema):
    spec = make_spec(raw={"*xyz": {"Charge": 1}})
    with pytest.raises(ValueError, match="written by the composer"):
        compose(schema, spec)


def test_compose_without_geometry_fails(schema):
    with pytest.raises(ValueError, match="needs a geometry"):
        compose(schema, make_spec(), atoms=None)


def test_a_typical_calculation_passes_the_validator(schema):
    spec = make_spec(
        module="GEOMETRY_OPTIMISATION",
        module_args={"MaxIter": 100},
        parameters={
            "BASIS": "def2-TZVP",
            "CHARGE": 0,
            "MULTIPLICITY": 1,
            "REFERENCE": "RKS",
            "DISPERSION": "D3BJ",
            "SOLVATION": {"variant": "SMD", "SMDsolvent": "water"},
            "SCF": {"Convergence": "Tight", "MaxIter": 200},
        },
    )
    # strict raises on the first issue, so an empty list means a clean calculation.
    assert validate(spec, schema, atoms=molecule("H2O"), mode="strict") == []


def test_a_periodic_geometry_is_refused(schema):
    issues = validate(make_spec(), schema, atoms=bulk("Si"), mode="warn")
    assert any("MOLECULE" in issue.message for issue in issues)
