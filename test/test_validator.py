"""Tests of amac.parameter.validator on the dummy doc.json."""

import warnings
from types import SimpleNamespace

import pytest

from amac.assets._dummy.dummy import DummySoftware
from amac.exceptions import ValidationError
from amac.parameter.parameters import CalculationSpec
from amac.parameter.schema import Schema, load
from amac.parameter.validator import Issue, validate


@pytest.fixture
def schema() -> Schema:
    return load(DummySoftware.DOC)


def make_spec(**overrides) -> CalculationSpec:
    kwargs = {
        "method": "DFT",
        "method_args": {"variant": "PBE"},
        "module": "SINGLE_POINT",
        "parameters": {"BASIS": "sto-3g"},
    }
    return CalculationSpec.from_kwargs(**kwargs | overrides)


def issue_paths(spec: CalculationSpec, schema: Schema, atoms=None) -> list[str]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        issues = validate(spec, schema, mode="warn", atoms=atoms)
    return [issue.path for issue in issues]


def test_valid_spec_has_no_issue(schema):
    assert validate(make_spec(), schema) == []


def test_unknown_method(schema):
    assert issue_paths(make_spec(method="CCSD"), schema) == ["method"]


def test_unknown_variant(schema):
    spec = make_spec(method_args={"variant": "PBE0"})
    assert issue_paths(spec, schema) == ["method_args.variant"]


def test_unknown_module(schema):
    assert issue_paths(make_spec(module="MD"), schema) == ["module"]


def test_unknown_option(schema):
    spec = make_spec(parameters={"BASIS": "sto-3g", "SCF": {"Damping": 0.5}})
    assert issue_paths(spec, schema) == ["parameters.SCF.Damping"]


def test_aliases_are_resolved(schema):
    spec = make_spec(
        method="dft",
        method_args={"VARIANT": "pbe96", "multiplicity": 2},
        module="sp",
        parameters={"basis": "sto-3g", "scf_options": {"maxiterations": 50}},
    )
    assert validate(spec, schema) == []


@pytest.mark.parametrize(
    ("scf", "path"),
    [
        ({"MaxIter": 0}, "parameters.SCF.MaxIter"),
        ({"Mixer": "Pulay"}, "parameters.SCF.Mixer"),
        ({"MaxIter": "ten"}, "parameters.SCF.MaxIter"),
    ],
    ids=["out-of-range", "not-in-values", "wrong-type"],
)
def test_invalid_value(schema, scf, path):
    spec = make_spec(parameters={"BASIS": "sto-3g", "SCF": scf})
    assert issue_paths(spec, schema) == [path]


def test_mandatory_missing(schema):
    assert issue_paths(make_spec(parameters={}), schema) == ["parameters.BASIS"]


def test_mandatory_if_not_satisfied(schema):
    spec = make_spec(parameters={"BASIS": "sto-3g", "SCF": {"Mixer": "Simple"}})
    assert issue_paths(spec, schema) == ["parameters.SCF.MixingParameter"]


def test_mandatory_if_satisfied(schema):
    scf = {"Mixer": "Simple", "MixingParameter": 0.3}
    spec = make_spec(parameters={"BASIS": "sto-3g", "SCF": scf})
    assert issue_paths(spec, schema) == []


def test_excluded_options(schema):
    parameters = {"BASIS": "sto-3g", "SOLVENT": "water", "EPSILON": 80.0}
    spec = make_spec(parameters=parameters)
    assert issue_paths(spec, schema) == ["parameters.SOLVENT", "parameters.EPSILON"]


def test_option_excluded_by_method(schema):
    parameters = {"BASIS": "sto-3g", "DISPERSION": "D3"}
    assert issue_paths(make_spec(parameters=parameters), schema) == []
    spec = make_spec(method="HF", method_args={}, parameters=parameters)
    assert issue_paths(spec, schema) == ["parameters.DISPERSION"]


def test_requires_of_module(schema):
    assert issue_paths(make_spec(module="OPT"), schema) == ["module"]
    parameters = {"BASIS": "sto-3g", "OUTPUT": {"WriteForces": True}}
    assert issue_paths(make_spec(module="OPT", parameters=parameters), schema) == []


@pytest.mark.parametrize(
    ("overrides", "pbc", "path"),
    [
        ({"module": "OPT"}, (False, False, True), "module"),
        ({"method_args": {"variant": "B3LYP"}}, True, "method_args.variant"),
    ],
)
def test_periodic_incompatible(schema, overrides, pbc, path):
    parameters = {"BASIS": "sto-3g", "OUTPUT": {"WriteForces": True}}
    spec = make_spec(parameters=parameters, **overrides)
    assert issue_paths(spec, schema, SimpleNamespace(pbc=pbc)) == [path]
    assert issue_paths(spec, schema, SimpleNamespace(pbc=[False] * 3)) == []


def test_atoms_without_pbc(schema):
    with pytest.raises(TypeError, match="pbc"):
        validate(make_spec(), schema, atoms=object())


def test_raw_is_ignored(schema):
    spec = make_spec(raw={"NotAnOption": -1, "SCF": "anything"})
    assert validate(spec, schema) == []


def test_strict_mode_raises_all_issues(schema):
    spec = make_spec(method="CCSD", module="MD")
    with pytest.raises(ValidationError, match="method") as excinfo:
        validate(spec, schema, mode="strict")
    assert "module" in str(excinfo.value)


def test_warn_mode_warns_and_returns_issues(schema):
    with pytest.warns(UserWarning, match="module"):
        issues = validate(make_spec(module="MD"), schema, mode="warn")
    assert len(issues) == 1
    assert isinstance(issues[0], Issue)
    assert issues[0].level == "error"


def test_off_mode_does_nothing(schema):
    assert validate(make_spec(method="CCSD"), schema, mode="off") == []


def test_unknown_mode(schema):
    with pytest.raises(ValueError, match="mode"):
        validate(make_spec(), schema, mode="lenient")
