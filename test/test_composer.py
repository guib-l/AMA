"""Tests of amac.parameter.composer."""

from pathlib import Path

import pytest
from ase.build import molecule

from amac.assets.dftbplus.dftbplus import DftbPlus
from amac.engine.context import RunContext
from amac.exceptions import ValidationError
from amac.parameter.composer import (
    FlatComposer,
    InputTree,
    KeywordBlockComposer,
    NamelistComposer,
    Node,
    TreeComposer,
    get_composer,
    render_unit,
    translate,
)
from amac.parameter.parameters import CalculationSpec, ExecutionSpec
from amac.parameter.schema import load

INPUT_FILE = "dftb_in.hsd"

HSD_FORMAT = {
    "ASSIGN": " = ",
    "OPEN": "{",
    "CLOSE": "}",
    "PADDING": "  ",
    "SEPARATOR": " ",
    "BOOLEAN": ["Yes", "No"],
    "MODIFIER": "[{unit}]",
}


def make_spec(**overrides) -> CalculationSpec:
    kwargs = {
        "method": "DFT",
        "method_args": {"variant": "PBE"},
        "module": "SINGLE_POINT",
        "parameters": {"BASIS": "sto-3g"},
    }
    return CalculationSpec.from_kwargs(**kwargs | overrides)


def make_ctx(directory: Path, spec: CalculationSpec | None = None) -> RunContext:
    exec_spec = ExecutionSpec(cpu=2, ram=1000)
    return RunContext(None, spec or make_spec(), exec_spec, directory)


def hsd(value=None, unit=None, **children) -> Node:
    return Node(value=value, unit=unit, format=dict(HSD_FORMAT), children=children)


def hsd_tree(raw=None, **nodes) -> InputTree:
    return InputTree(nodes=nodes, raw=raw, format=dict(HSD_FORMAT))


@pytest.mark.parametrize(
    ("unit", "fmt", "expected"),
    [
        ("energy", {"UNITS": {"energy": "eV"}, "MODIFIER": "[{unit}]"}, "[eV]"),
        ("Hartree", {"UNITS": {"energy": "eV"}, "MODIFIER": "[{unit}]"}, "[Hartree]"),
        ("energy", {"UNITS": {"energy": "eV"}}, "eV"),
        (None, {"MODIFIER": "[{unit}]"}, None),
    ],
)
def test_render_unit(unit, fmt, expected):
    assert render_unit(unit, fmt) == expected


def test_tree_render_hsd():
    tree = hsd_tree(
        raw=["ParserOptions = {", "  ParserVersion = 14", "}"],
        Hamiltonian=hsd(
            "DFTB",
            DFTB=hsd(
                SCC=hsd(True),
                Mixer=hsd("Broyden", Broyden=hsd(MixingParameter=hsd(0.2))),
                Filling=hsd("Fermi", Temperature=hsd(300, unit="K")),
                KPointsAndWeights=hsd(
                    "SupercellFolding",
                    supercellfolding=hsd([[2, 0, 0], [0, 2, 0], [0.5, 0.5, 0.5]]),
                ),
                SlaterKosterFiles=hsd(
                    "Type2FileNames",
                    Type2FileNames=hsd(Prefix=hsd("./sk dir/"), Suffix=hsd(".skf")),
                ),
            ),
        ),
        Driver=hsd(),
        Geometry=hsd("GenFormat", GenFormat=hsd()),
        Analysis=hsd(
            WriteBandOut=hsd(False),
            ProjectStates=hsd(Region=hsd(Atoms=hsd([1, 2, 3]), Label=hsd(""))),
        ),
        LatticeVectors=hsd([[1.0, 0.0], [0.0, 1.0]], unit="Angstrom"),
    )
    expected = """\
Hamiltonian = DFTB {
  SCC = Yes
  Mixer = Broyden {
    MixingParameter = 0.2
  }
  Filling = Fermi {
    Temperature [K] = 300
  }
  KPointsAndWeights = SupercellFolding {
    2 0 0
    0 2 0
    0.5 0.5 0.5
  }
  SlaterKosterFiles = Type2FileNames {
    Prefix = "./sk dir/"
    Suffix = .skf
  }
}
Driver = {}
Geometry = GenFormat {}
Analysis = {
  WriteBandOut = No
  ProjectStates = {
    Region = {
      Atoms = 1 2 3
      Label = ""
    }
  }
}
LatticeVectors [Angstrom] = {
  1.0 0.0
  0.0 1.0
}
ParserOptions = {
  ParserVersion = 14
}
"""
    before = tree.to_dict()
    assert TreeComposer().render(tree) == expected
    assert tree.to_dict() == before


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("DFTB", "Name = DFTB\n"),
        ("", 'Name = ""\n'),
        ("two words", 'Name = "two words"\n'),
        ("a\tb", 'Name = "a\tb"\n'),
        *((f"a{char}b", f'Name = "a{char}b"\n') for char in "{}=[]#"),
    ],
)
def test_tree_render_quoting(value, expected):
    assert TreeComposer().render(hsd_tree(Name=hsd(value))) == expected


def test_tree_render_rejects_double_quote():
    with pytest.raises(ValueError, match="containing"):
        TreeComposer().render(hsd_tree(Name=hsd('say "hi"')))


def test_tree_render_rejects_keywords():
    tree = hsd_tree(Driver=hsd())
    tree.keywords = ["GFN2-xTB"]
    with pytest.raises(ValueError, match="GFN2-xTB"):
        TreeComposer().render(tree)


def test_tree_render_raw_str():
    tree = hsd_tree(raw="Parallel = {}", Driver=hsd())
    assert TreeComposer().render(tree) == "Driver = {}\nParallel = {}\n"


def test_tree_render_raw_dict_merges_into_copy():
    tree = hsd_tree(
        raw={"hamiltonian": {"dftb": {"Charge": -1}}, "Options": {"WriteHS": True}},
        Hamiltonian=hsd("DFTB", DFTB=hsd(SCC=hsd(True))),
    )
    before = tree.to_dict()
    expected = """\
Hamiltonian = DFTB {
  SCC = Yes
  Charge = -1
}
Options = {
  WriteHS = Yes
}
"""
    assert TreeComposer().render(tree) == expected
    assert tree.to_dict() == before


def test_tree_render_raw_dict_conflict():
    tree = hsd_tree(
        raw={"HAMILTONIAN": {"DFTB": {"SCC": False}}},
        Hamiltonian=hsd("DFTB", DFTB=hsd(SCC=hsd(True))),
    )
    with pytest.raises(ValidationError, match="Conflicting values at HAMILTONIAN"):
        TreeComposer().render(tree)


@pytest.mark.parametrize(
    ("syntax", "composer_cls"),
    [
        ("KEYWORD_BLOCK", KeywordBlockComposer),
        ("TREE", TreeComposer),
        ("namelist", NamelistComposer),
        ("FLAT", FlatComposer),
    ],
)
def test_get_composer(syntax, composer_cls):
    assert get_composer(syntax) is composer_cls


def test_get_composer_unknown_syntax():
    with pytest.raises(ValueError, match="'API'.*Available: KEYWORD_BLOCK"):
        get_composer("API")


def dftbp_spec(**overrides) -> CalculationSpec:
    kwargs = {
        "method": "TIGHT_BINDING",
        "method_args": {"variant": "DFTB2", "MaxAngularMomentum": {"O": "p", "H": "s"}},
        "module": "SINGLE_POINT",
        "parameters": {"SLATER_KOSTER_FILES": {"variant": "Type2FileNames"}},
    }
    return CalculationSpec.from_kwargs(**kwargs | overrides)


def test_fileio_prepare_writes_a_deterministic_input(tmp_path, dftbp_configured):
    """``FileIOSoftware.prepare`` composes, writes, and records what it wrote."""
    spec = dftbp_spec(raw={"ParserOptions": {"ParserVersion": 14}})
    contents = []
    for name in ("first", "second"):
        directory = tmp_path / name
        directory.mkdir()
        ctx = RunContext(molecule("H2O"), spec, ExecutionSpec(cpu=2), directory)
        DftbPlus().prepare(ctx)
        assert ctx.input_files == {INPUT_FILE: directory / INPUT_FILE}
        contents.append(ctx.input_files[INPUT_FILE].read_text(encoding="utf-8"))
    # The same spec always gives the same input file, byte for byte.
    assert contents[0] == contents[1]
    assert "SlaterKosterFiles = Type2FileNames {" in contents[0]
    assert "ParserVersion = 14" in contents[0]  # raw keywords are kept
    assert str(dftbp_configured) in contents[0]  # Prefix, taken from BASIS


def test_fileio_prepare_refuses_a_missing_directory(tmp_path, dftbp_configured):
    ctx = RunContext(
        molecule("H2O"), dftbp_spec(), ExecutionSpec(), tmp_path / "missing"
    )
    with pytest.raises(FileNotFoundError):
        DftbPlus().prepare(ctx)


# Translation of the doc.json features into the intermediate tree.

FOLDING = [[4, 0, 0], [0, 4, 0], [0, 0, 4], [0.5, 0.5, 0.5]]


@pytest.fixture
def dftbplus_schema():
    return load(DftbPlus.DOC)


def node_at(tree, *path):
    node = tree.nodes[path[0]]
    for part in path[1:]:
        node = node.children[part]
    return node


def test_a_variant_writes_the_options_it_imposes(dftbplus_schema):
    """``SETS`` of the DFTB2 variant reaches the tree, without being in the spec."""
    scc = node_at(
        translate(dftbp_spec(), dftbplus_schema), "Hamiltonian", "DFTB", "SCC"
    )
    assert scc.value is True


def test_option_variants_reach_their_declared_location(dftbplus_schema):
    spec = dftbp_spec(
        parameters={
            "SLATER_KOSTER_FILES": {"variant": "Type2FileNames"},
            "KPOINTS": {"SupercellFolding": FOLDING},
            "SMEARING": {"Fermi": {"Temperature": 0.001}},
        }
    )
    dftb = node_at(translate(spec, dftbplus_schema), "Hamiltonian", "DFTB").children
    assert dftb["SlaterKosterFiles"].value == "Type2FileNames"
    assert dftb["KPointsAndWeights"].value == "SupercellFolding"
    assert dftb["KPointsAndWeights"].children["SupercellFolding"].value == FOLDING
    temperature = dftb["Filling"].children["Fermi"].children["Temperature"]
    assert temperature.value == pytest.approx(0.001, abs=1e-15)


def test_a_bare_value_fills_the_scalar_argument_of_the_default_choice(dftbplus_schema):
    """``SMEARING`` declares ``SCALAR``: 0.001 is Fermi at that temperature."""
    spec = dftbp_spec(
        parameters={
            "SLATER_KOSTER_FILES": {"variant": "Type2FileNames"},
            "SMEARING": 0.001,
        }
    )
    filling = node_at(translate(spec, dftbplus_schema), "Hamiltonian", "DFTB", "Filling")
    assert filling.value == "Fermi"
    temperature = filling.children["Fermi"].children["Temperature"]
    assert temperature.value == pytest.approx(0.001, abs=1e-15)
    assert temperature.unit == "energy"
    # Only the named argument is written: the other DEFAULT values stay out.
    assert list(filling.children["Fermi"].children) == ["Temperature"]
