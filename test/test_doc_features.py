"""Tests of option variants, SETS, COMPANION and COMMON_ARGUMENTS (TODO-1, point 3)."""

import warnings
from pathlib import Path

import pytest

import amac
from amac.assets._dummy.dummy import DummySoftware
from amac.exceptions import ValidationError
from amac.parameter.composer import translate
from amac.parameter.parameters import CalculationSpec
from amac.parameter.schema import load
from amac.parameter.validator import validate

DFTBPLUS_DOC = Path(amac.__file__).parent / "assets" / "dftbplus" / "doc.json"
FOLDING = [[4, 0, 0], [0, 4, 0], [0, 0, 4], [0.5, 0.5, 0.5]]


@pytest.fixture
def dummy():
    return load(DummySoftware.DOC)


@pytest.fixture
def dftbplus():
    return load(DFTBPLUS_DOC)


def dummy_spec(**overrides) -> CalculationSpec:
    kwargs = {
        "method": "DFT",
        "method_args": {"variant": "PBE"},
        "parameters": {"BASIS": "sto-3g"},
    }
    return CalculationSpec.from_kwargs(**kwargs | overrides)


def dftb_spec(method_args=None, **parameters) -> CalculationSpec:
    arguments = {"variant": "DFTB2", "MaxAngularMomentum": {"Si": "p"}}
    slater_koster = {"variant": "Type2FileNames", "Prefix": "pbc-0-3/"}
    return CalculationSpec.from_kwargs(
        method="TIGHT_BINDING",
        method_args=arguments | (method_args or {}),
        parameters={"SLATER_KOSTER_FILES": slater_koster} | parameters,
    )


def issue_paths(spec, schema) -> list[str]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return [issue.path for issue in validate(spec, schema, mode="warn")]


def node_at(tree, *path):
    node = tree.nodes[path[0]]
    for part in path[1:]:
        node = node.children[part]
    return node


def test_sets_fill_an_absent_option(dummy):
    spec = dummy_spec(method_args={"variant": "TPSSh"})
    assert validate(spec, dummy) == []
    assert node_at(translate(spec, dummy), "Hamiltonian", "DFT", "Grid").value == "Fine"
    same = dummy_spec(method_args={"variant": "tpssh", "grid": "fine"})
    assert validate(same, dummy) == []


def test_sets_contrary_value(dummy):
    spec = dummy_spec(method_args={"variant": "TPSSh", "Grid": "Coarse"})
    with pytest.raises(ValidationError, match="variant 'TPSSH' sets Grid to 'Fine'"):
        validate(spec, dummy)
    with pytest.warns(UserWarning, match="method_args.Grid: variant 'TPSSH' sets Grid"):
        validate(spec, dummy, mode="warn")
    assert validate(spec, dummy, mode="off") == []
    tree = translate(spec, dummy)
    assert node_at(tree, "Hamiltonian", "DFT", "Grid").value == "Coarse"


def test_parameter_variant(dummy):
    integration = {"variant": "Lebedev", "Points": 302}
    spec = dummy_spec(parameters={"BASIS": "sto-3g", "INTEGRATION": integration})
    assert validate(spec, dummy) == []
    node = translate(spec, dummy).nodes["Integration"]
    assert node.value == "Lebedev"
    assert node.children["Lebedev"].children["Points"].value == 302
    assert node.children["Pruning"].value is True


@pytest.mark.parametrize(
    ("integration", "path"),
    [
        ({"variant": "Gauss"}, "parameters.INTEGRATION.variant"),
        ({"variant": "Lebedev", "Points": 1}, "parameters.INTEGRATION.Points"),
        ({"variant": "becke_grid", "Points": 302}, "parameters.INTEGRATION.Points"),
    ],
    ids=["unknown-variant", "out-of-range", "not-in-variant"],
)
def test_invalid_parameter_variant(dummy, integration, path):
    spec = dummy_spec(parameters={"BASIS": "sto-3g", "INTEGRATION": integration})
    assert issue_paths(spec, dummy) == [path]


def test_choice_designating_a_variant(dummy):
    spec = dummy_spec(parameters={"BASIS": "sto-3g", "SAMPLING": {"Grid": [4, 4, 4]}})
    assert validate(spec, dummy) == []
    sampling = translate(spec, dummy).nodes["Sampling"]
    assert (sampling.value, sampling.children["Grid"].value) == ("Grid", [4, 4, 4])
    unknown = dummy_spec(parameters={"BASIS": "sto-3g", "SAMPLING": "Monkhorst"})
    assert issue_paths(unknown, dummy) == ["parameters.SAMPLING"]
    wrong_type = dummy_spec(parameters={"BASIS": "sto-3g", "SAMPLING": {"Grid": "4"}})
    assert issue_paths(wrong_type, dummy) == ["parameters.SAMPLING.Grid"]


def test_companion(dummy):
    parameters = {"BASIS": "sto-3g", "DISPERSION": "D4", "ThreeBody": True}
    assert issue_paths(dummy_spec(parameters=parameters), dummy) == [
        "parameters.DispersionScaling"
    ]
    spec = dummy_spec(parameters=parameters | {"DispersionScaling": 0.8})
    assert validate(spec, dummy) == []
    dft = node_at(translate(spec, dummy), "Hamiltonian", "DFT").children
    assert (dft["DispersionScaling"].value, dft["ThreeBody"].value) == (0.8, True)
    out_of_range = dummy_spec(parameters={"BASIS": "sto-3g", "DispersionScaling": 5.0})
    assert issue_paths(out_of_range, dummy) == ["parameters.DISPERSIONSCALING"]


def test_common_arguments(dummy):
    scf = {"Mixer": {"Broyden": {"History": 8}}}
    spec = dummy_spec(parameters={"BASIS": "sto-3g", "SCF": scf})
    assert validate(spec, dummy) == []
    mixer = node_at(translate(spec, dummy), "Scf", "Mixer")
    assert mixer.value == "Broyden"
    assert mixer.children["Broyden"].children["History"].value == 8
    for options, name in (({"History": 0}, "History"), ({"Depth": 3}, "Depth")):
        scf = {"Mixer": {"Broyden": options}}
        spec = dummy_spec(parameters={"BASIS": "sto-3g", "SCF": scf})
        assert issue_paths(spec, dummy) == [f"parameters.SCF.Mixer.Broyden.{name}"]


def test_dftbplus_sets_scc(dftbplus):
    spec = dftb_spec()
    assert validate(spec, dftbplus) == []
    scc = node_at(translate(spec, dftbplus), "Hamiltonian", "DFTB", "SCC")
    assert scc.value is True
    with pytest.raises(ValidationError, match="variant 'DFTB2' sets SCC to True"):
        validate(dftb_spec({"SCC": False}), dftbplus)


def test_dftbplus_parameter_features(dftbplus):
    spec = dftb_spec(
        KPOINTS={"SupercellFolding": FOLDING},
        FILLING={"Fermi": {"Temperature": 0.001}},
    )
    assert validate(spec, dftbplus) == []
    dftb = node_at(translate(spec, dftbplus), "Hamiltonian", "DFTB").children
    slater_koster = dftb["SlaterKosterFiles"]
    assert slater_koster.value == "Type2FileNames"
    prefix = slater_koster.children["Type2FileNames"].children["Prefix"]
    assert prefix.value == "pbc-0-3/"
    assert dftb["KPointsAndWeights"].value == "SupercellFolding"
    assert dftb["KPointsAndWeights"].children["SupercellFolding"].value == FOLDING
    temperature = dftb["Filling"].children["Fermi"].children["Temperature"]
    assert temperature.value == pytest.approx(0.001, abs=1e-15)


@pytest.mark.parametrize(
    ("parameters", "path"),
    [
        ({"KPOINTS": {"SuperFolding": FOLDING}}, "parameters.KPOINTS"),
        (
            {"SLATER_KOSTER_FILES": {"variant": "Type2FileNames", "Prefixx": "x"}},
            "parameters.SLATER_KOSTER_FILES.Prefixx",
        ),
        (
            {"FILLING": {"Fermi": {"Temprature": 0.001}}},
            "parameters.FILLING.Fermi.Temprature",
        ),
        (
            {"SPIN_POLARISATION": {"Colinear": {"UnpairedElectrons": 2.0}}},
            "parameters.SpinConstants",
        ),
    ],
    ids=["unknown-kpoints-variant", "unknown-variant-argument", "common-argument",
         "companion"],
)
def test_dftbplus_invalid(dftbplus, parameters, path):
    assert issue_paths(dftb_spec(**parameters), dftbplus) == [path]
