"""Tests of amac.parameter.validator, against the real ``doc.json`` files.

The rules checked here are generic (variants, ``SETS``, ``COMMON_ARGUMENTS``,
``MANDATORY``, ``REQUIRES``, ``PERIODIC``, types and ranges); DFTB+ and deMonNano
only provide the declarations they apply to.
"""

import json
import warnings
from pathlib import Path

import pytest
from ase import Atoms
from ase.build import bulk, molecule

import amac
from amac.exceptions import ValidationError
from amac.parameter.parameters import CalculationSpec
from amac.parameter.schema import REQUIRED_KEYS, load
from amac.parameter.validator import MODES, Issue, validate

ASSETS = Path(amac.__file__).parent / "assets"
DFTBPLUS_DOC = ASSETS / "dftbplus" / "doc.json"
DEMONNANO_DOC = ASSETS / "demonnano" / "doc.json"
FOLDING = [[4, 0, 0], [0, 4, 0], [0, 0, 4], [0.5, 0.5, 0.5]]


@pytest.fixture
def dftbplus():
    return load(DFTBPLUS_DOC)


@pytest.fixture
def demonnano():
    return load(DEMONNANO_DOC)


def dftb_spec(method_args=None, module="SINGLE_POINT", **parameters) -> CalculationSpec:
    """Return a valid DFTB+ specification, altered by the arguments."""
    arguments = {"variant": "DFTB2", "MaxAngularMomentum": {"Si": "p"}}
    slater_koster = {"variant": "Type2FileNames"}
    return CalculationSpec.from_kwargs(
        method="TIGHT_BINDING",
        method_args=arguments | (method_args or {}),
        module=module,
        parameters={"SLATER_KOSTER_FILES": slater_koster} | parameters,
    )


def issues(spec, schema, atoms=None) -> list[Issue]:
    """Return the issues of ``spec`` without letting the warnings escape."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return validate(spec, schema, mode="warn", atoms=atoms)


def paths(spec, schema, atoms=None) -> list[str]:
    return [issue.path for issue in issues(spec, schema, atoms)]


# Modes.


def test_valid_specification_has_no_issue(dftbplus):
    assert validate(dftb_spec(), dftbplus) == []


def test_strict_lists_every_issue(dftbplus):
    spec = dftb_spec({"SCC": False}, KPOINTS={"SuperFolding": FOLDING})
    with pytest.raises(ValidationError) as info:
        validate(spec, dftbplus, mode="strict")
    message = str(info.value)
    assert message.startswith("Invalid calculation for DFTBP:")
    assert message.count("  - ") == 2


def test_warn_emits_one_warning_per_issue(dftbplus):
    spec = dftb_spec({"SCC": False}, KPOINTS={"SuperFolding": FOLDING})
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        found = validate(spec, dftbplus, mode="warn")
    assert len(found) == len(caught) == 2
    assert all(isinstance(issue, Issue) and issue.level == "error" for issue in found)


def test_off_skips_the_checks(dftbplus):
    assert validate(dftb_spec({"SCC": False}), dftbplus, mode="off") == []


def test_unknown_mode(dftbplus):
    assert MODES == ("strict", "warn", "off")
    with pytest.raises(ValueError, match="Unknown validation mode 'lenient'"):
        validate(dftb_spec(), dftbplus, mode="lenient")


# Methods, modules and their variants.


@pytest.mark.parametrize(
    ("kwargs", "path", "match"),
    [
        ({"method": "NOPE"}, "method", "Unknown METHODS entry 'NOPE'"),
        ({"module": "NOPE"}, "module", "Unknown MODULES entry 'NOPE'"),
    ],
    ids=["method", "module"],
)
def test_unknown_method_or_module(dftbplus, kwargs, path, match):
    spec = CalculationSpec.from_kwargs(
        **{"method": "TIGHT_BINDING", "module": "SINGLE_POINT"} | kwargs
    )
    issue = issues(spec, dftbplus)[0]
    assert issue.path == path
    assert match in issue.message


def test_unknown_variant(dftbplus):
    [issue] = issues(dftb_spec({"variant": "DFTB9"}), dftbplus)
    assert issue.path == "method_args.variant"
    assert "Unknown variant" in issue.message


def test_variant_must_be_a_string(dftbplus):
    [issue] = issues(dftb_spec({"variant": 2}), dftbplus)
    assert issue.message == "variant must be a str, got int"


def test_a_variant_imposes_its_options(dftbplus):
    """``SETS`` of the DFTB2 variant: SCC is on, and cannot be turned off."""
    assert validate(dftb_spec(), dftbplus) == []
    with pytest.raises(ValidationError, match="variant 'DFTB2' sets SCC to True"):
        validate(dftb_spec({"SCC": False}), dftbplus)
    # The same value as the one imposed is accepted.
    assert validate(dftb_spec({"SCC": True}), dftbplus) == []


def test_unknown_argument_is_reported_with_its_path(dftbplus):
    assert paths(dftb_spec({"SCCTolerence": 1e-6}), dftbplus) == [
        "method_args.SCCTolerence"
    ]


# Options: variants, common arguments and companions.


def test_option_variants_and_their_arguments(dftbplus):
    spec = dftb_spec(
        KPOINTS={"SupercellFolding": FOLDING},
        SMEARING={"Fermi": {"Temperature": 0.001}},
    )
    assert validate(spec, dftbplus) == []


@pytest.mark.parametrize(
    ("parameters", "path"),
    [
        ({"KPOINTS": {"SuperFolding": FOLDING}}, "parameters.KPOINTS"),
        (
            {"SLATER_KOSTER_FILES": {"variant": "Type2FileNames", "Prefixx": "x"}},
            "parameters.SLATER_KOSTER_FILES.Prefixx",
        ),
        (
            {"SLATER_KOSTER_FILES": {"variant": "Type2FileNames", "Prefix": "x/"}},
            "parameters.SLATER_KOSTER_FILES.Prefix",
        ),
        (
            {"SMEARING": {"Fermi": {"Temprature": 0.001}}},
            "parameters.SMEARING.Fermi.Temprature",
        ),
        (
            {"SPIN_POLARISATION": {"Colinear": {"UnpairedElectrons": 2.0}}},
            "parameters.SpinConstants",
        ),
    ],
    ids=[
        "unknown-kpoints-variant",
        "unknown-variant-argument",
        "prefix-from-basis",
        "common-argument",
        "companion",
    ],
)
def test_invalid_options(dftbplus, parameters, path):
    assert paths(dftb_spec(**parameters), dftbplus) == [path]


def test_a_bare_value_goes_to_the_scalar_argument(dftbplus):
    """``SMEARING`` declares ``SCALAR``: a bare value is its default choice."""
    assert validate(dftb_spec(SMEARING=0.001), dftbplus) == []
    assert validate(dftb_spec(FILLING=0.001), dftbplus) == []


def test_a_bare_value_is_checked_like_the_argument_it_fills(dftbplus):
    [issue] = issues(dftb_spec(SMEARING="0.001 eV"), dftbplus)
    assert issue.path == "parameters.SMEARING"
    assert "'0.001 eV' is not one of: " in issue.message
    [issue] = issues(dftb_spec(SMEARING=[1, 2]), dftbplus)
    assert issue.path == "parameters.SMEARING.Fermi.Temperature"
    assert "expected REAL, got list" in issue.message


def test_scalar_without_a_usable_default_is_a_doc_error(tmp_path):
    """``SCALAR`` needs a ``DEFAULT`` choice to carry the bare value."""
    doc = {key: {} for key in REQUIRED_KEYS} | {
        "SOFTWARE": "X",
        "VERSION": "0",
        "SYNTAX": "FLAT",
        "EXECUTION": [],
        "MODULES": {"SINGLE_POINT": {}},
        "METHODS": {"HF": {}},
        "PARAMETERS": {
            "SMEARING": {
                "TYPE": "CHOICE",
                "SCALAR": "Temperature",
                "ARGUMENTS": {"Fermi": {"TYPE": "BLOCK"}},
                "COMMON_ARGUMENTS": {"Temperature": {"TYPE": "REAL"}},
            }
        },
    }
    path = tmp_path.joinpath("doc.json")
    path.write_text(json.dumps(doc), encoding="utf-8")
    spec = CalculationSpec.from_kwargs(
        method="HF", module="SINGLE_POINT", parameters={"SMEARING": 0.001}
    )
    [issue] = issues(spec, load(path))
    assert issue.path == "parameters.SMEARING"
    assert "needs a DEFAULT choice to carry Temperature" in issue.message


def test_unknown_parameter(dftbplus):
    [issue] = issues(dftb_spec(SOLVATION_MODEL="cpcm"), dftbplus)
    assert issue.path == "parameters.SOLVATION_MODEL"
    assert issue.message.startswith("Unknown option 'SOLVATION_MODEL'. Available: ")


def test_option_given_twice_under_two_spellings(dftbplus):
    spec = dftb_spec({"SCCTolerance": 1e-6, "scctolerance": 1e-8})
    [issue] = issues(spec, dftbplus)
    assert "given several times" in issue.message


def test_option_names_must_be_strings(dftbplus):
    [issue] = issues(dftb_spec({3: "p"}), dftbplus)
    assert issue.message == "option names must be str, got 3"


# Types, values and ranges.


def test_wrong_type(dftbplus):
    [issue] = issues(dftb_spec({"SCCTolerance": "tight"}), dftbplus)
    assert issue.path == "method_args.SCCTolerance"
    assert "expected REAL, got str" in issue.message


def test_value_outside_the_declared_range(dftbplus):
    """``SMEARING`` declares the order of Methfessel-Paxton in [1, 10]."""
    spec = dftb_spec(SMEARING={"MethfesselPaxton": {"Order": 42}})
    [issue] = issues(spec, dftbplus)
    assert issue.path == "parameters.SMEARING.MethfesselPaxton.Order"
    assert "outside [1, 10]" in issue.message


def test_value_not_in_the_declared_list(dftbplus):
    """``MIXER`` declares the mixers DFTB+ knows: no other name is accepted."""
    [issue] = issues(dftb_spec(MIXER={"Nope": {}}), dftbplus)
    assert issue.path == "parameters.MIXER"
    assert "'Nope' is not one of: Broyden, Anderson, DIIS, Simple" in issue.message


# Mandatory options and module requirements.


def test_mandatory_option_missing(dftbplus):
    spec = CalculationSpec.from_kwargs(
        method="TIGHT_BINDING",
        method_args={"variant": "DFTB2"},
        parameters={"SLATER_KOSTER_FILES": {"variant": "Type2FileNames"}},
    )
    [issue] = issues(spec, dftbplus)
    assert issue.path == "method_args.MaxAngularMomentum"
    assert issue.message == "mandatory option is missing"


def test_module_requirements(demonnano):
    """deMonNano needs its Slater-Koster block, whatever the module."""
    spec = CalculationSpec.from_kwargs(
        method="TIGHT_BINDING",
        method_args={"variant": "SCC-DFTB"},
        module="SINGLE_POINT",
    )
    assert any("SLATER_KOSTER_FILES" in issue.path for issue in issues(spec, demonnano))


# Geometry.


def test_molecule_only_module_refuses_a_periodic_cell(demonnano):
    """Every module of deMonNano is declared MOLECULE."""
    spec = CalculationSpec.from_kwargs(
        method="TIGHT_BINDING",
        method_args={"variant": "SCC-DFTB"},
        module="SINGLE_POINT",
        parameters={"SLATER_KOSTER_FILES": {"PTYPE": "BIO"}},
    )
    assert issues(spec, demonnano, atoms=molecule("H2O")) == []
    crystal = bulk("Si", "diamond", a=5.43)
    [issue] = issues(spec, demonnano, atoms=crystal)
    assert issue.message == "atoms.pbc is periodic, MOLECULE only"


def test_both_accepts_a_molecule_and_a_crystal(dftbplus):
    """The modules of DFTB+ are declared BOTH: the geometry never refuses them."""
    spec = dftb_spec()
    assert issues(spec, dftbplus, atoms=molecule("H2O")) == []
    assert issues(spec, dftbplus, atoms=bulk("Si", "diamond", a=5.43)) == []


def test_geometry_is_only_checked_when_given(demonnano):
    spec = CalculationSpec.from_kwargs(
        method="TIGHT_BINDING",
        method_args={"variant": "SCC-DFTB"},
        parameters={"SLATER_KOSTER_FILES": {"PTYPE": "BIO"}},
    )
    assert validate(spec, demonnano) == []


def test_atoms_must_have_pbc(dftbplus):
    with pytest.raises(TypeError, match="pbc"):
        validate(dftb_spec(), dftbplus, atoms=object())


def test_pbc_may_be_a_single_flag(dftbplus):
    """A bool ``pbc``, as some geometry objects expose, is read like a sequence."""

    class Flagged:
        pbc = True

    spec = dftb_spec(KPOINTS={"SupercellFolding": FOLDING})
    assert validate(spec, dftbplus, atoms=Flagged()) == []
    assert validate(spec, dftbplus, atoms=Atoms("H", pbc=True, cell=[3, 3, 3])) == []
