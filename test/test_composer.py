"""Tests of amac.parameter.composer on the sample doc.json of test/fixtures."""

import json
from pathlib import Path

import pytest

from amac.assets._dummy.dummy import DummySoftware
from amac.engine.context import RunContext
from amac.engine.software import FileIOSoftware
from amac.exceptions import ValidationError
from amac.parameter.composer import (
    Composer,
    FlatComposer,
    InputTree,
    KeywordBlockComposer,
    NamelistComposer,
    Node,
    TreeComposer,
    get_composer,
    inject_resources,
    render_bool,
    render_unit,
    translate,
)
from amac.parameter.parameters import CalculationSpec, ExecutionSpec
from amac.parameter.schema import Schema, load

SCHEMA_DOC = Path(__file__).parent / "fixtures" / "schema.json"
KEYWORD_BLOCK_DOC = Path(__file__).parent / "fixtures" / "keyword_block.json"
HSD_FORMAT = {
    "ASSIGN": " = ",
    "OPEN": "{",
    "CLOSE": "}",
    "PADDING": "  ",
    "SEPARATOR": " ",
    "BOOLEAN": ["Yes", "No"],
    "MODIFIER": "[{unit}]",
}

@pytest.fixture
def schema() -> Schema:
    return load(SCHEMA_DOC)


def make_spec(**overrides) -> CalculationSpec:
    kwargs = {
        "method": "DFT",
        "method_args": {"variant": "PBE"},
        "module": "SINGLE_POINT",
        "parameters": {"BASIS": "sto-3g"},
    }
    return CalculationSpec.from_kwargs(**kwargs | overrides)


def dummy_doc() -> dict:
    return json.loads(SCHEMA_DOC.read_text(encoding="utf-8"))


def write_schema(tmp_path: Path, doc: dict) -> Schema:
    path = tmp_path / "doc.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return load(path)


def make_ctx(directory: Path, spec: CalculationSpec | None = None) -> RunContext:
    exec_spec = ExecutionSpec(cpu=2, ram=1000)
    return RunContext(None, spec or make_spec(), exec_spec, directory)


def hsd(value=None, unit=None, **children) -> Node:
    return Node(value=value, unit=unit, format=dict(HSD_FORMAT), children=children)


def hsd_tree(raw=None, **nodes) -> InputTree:
    return InputTree(nodes=nodes, raw=raw, format=dict(HSD_FORMAT))


class NoOverrideSoftware(FileIOSoftware):
    DOC = SCHEMA_DOC

    def command(self, ctx):
        return []


class StaticComposer(Composer):
    def compose(self, spec, schema, atoms, exec_spec):
        return {"custom.txt": "custom\n"}


class OverrideSoftware(NoOverrideSoftware):
    composer_cls = StaticComposer


class PrefixedComposer(KeywordBlockComposer):
    KEYWORD_PREFIX = "!"


def test_translate_resolves_aliases(schema):
    spec = make_spec(
        method="hartree_fock",
        method_args={"charge": 1},
        module="sp",
        parameters={"basis": "sto-3g", "scf_options": {"maxiterations": 50}},
    )
    tree = translate(spec, schema)
    assert tree.nodes["Hamiltonian"].value == "HF"
    assert tree.nodes["Hamiltonian"].children["HF"].children["Charge"].value == 1
    assert tree.nodes["Driver"].value == "SinglePoint"
    assert tree.nodes["Basis"].value == "sto-3g"
    assert tree.nodes["Scf"].children["MaxIter"].value == 50


def test_translate_nested_paths(schema):
    spec = make_spec(
        method_args={"variant": "PBE", "Charge": 1},
        parameters={"BASIS": "sto-3g", "DISPERSION": "D3", "SOLVENT": "water"},
    )
    tree = translate(spec, schema)
    hamiltonian = tree.nodes["Hamiltonian"]
    assert hamiltonian.value == "DFT"
    assert list(hamiltonian.children) == ["DFT"]
    dft = hamiltonian.children["DFT"].children
    assert (dft["Charge"].value, dft["Dispersion"].value) == (1, "D3")
    assert tree.nodes["Solvation"].children["Solvent"].value == "water"
    assert tree.keywords == ["PBE"]


def test_format_defaults_merged_with_node_format(tmp_path):
    doc = dummy_doc()
    defaults = {"ASSIGN": " = ", "BOOLEAN": ["Yes", "No"]}
    doc["INPUT"]["FORMAT_DEFAULTS"] = defaults
    doc["PARAMETERS"]["OUTPUT"]["FORMAT"] = {"BOOLEAN": ["1", "0"]}
    parameters = {"BASIS": "sto-3g", "OUTPUT": {"WriteForces": True}}
    tree = translate(make_spec(parameters=parameters), write_schema(tmp_path, doc))
    assert tree.format == defaults
    assert tree.nodes["Basis"].format == defaults
    assert tree.nodes["Output"].format == {"ASSIGN": " = ", "BOOLEAN": ["1", "0"]}


def test_booleans(schema):
    parameters = {"BASIS": "sto-3g", "OUTPUT": {"WriteForces": True}}
    tree = translate(make_spec(parameters=parameters), schema)
    assert tree.nodes["Output"].children["WriteForces"].value is True
    assert render_bool(True, {"BOOLEAN": ["Yes", "No"]}) == "Yes"
    assert render_bool(False, {"BOOLEAN": ["Yes", "No"]}) == "No"
    assert render_bool(False, {}) == "false"


def test_units(schema):
    parameters = {"BASIS": "sto-3g", "SCF": {"Tolerance": 1e-5}}
    tree = translate(make_spec(parameters=parameters), schema)
    tolerance = tree.nodes["Scf"].children["Tolerance"]
    assert tolerance.unit == "energy"
    assert tolerance.value == pytest.approx(1e-5, rel=1e-12)
    assert tree.nodes["Basis"].unit is None


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


def test_inject_resources(schema):
    tree = translate(make_spec(), schema)
    inject_resources(tree, schema, ExecutionSpec(cpu=4, ram=2000))
    resources = tree.nodes["Resources"].children
    assert (resources["Cpu"].value, resources["Memory"].value) == (4, 2000)


def test_inject_resources_skips_missing(tmp_path, schema):
    tree = translate(make_spec(), schema)
    inject_resources(tree, schema, ExecutionSpec(cpu=4))
    assert list(tree.nodes["Resources"].children) == ["Cpu"]
    doc = dummy_doc()
    del doc["INPUT"]["RESOURCES"]
    tree = translate(make_spec(), schema)
    inject_resources(tree, write_schema(tmp_path, doc), ExecutionSpec(cpu=4))
    assert "Resources" not in tree.nodes


def test_raw_is_passed_unchanged(schema):
    raw = {"NotAnOption": -1, "Hamiltonian": ["anything"]}
    spec = make_spec(raw=raw)
    tree = translate(spec, schema)
    assert tree.raw == raw
    assert tree.raw is not spec.raw
    assert "NotAnOption" not in tree.nodes


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
    ("composer_cls", "first_line"),
    [
        (KeywordBlockComposer, "B3LYP Opt def2-SVP"),
        (PrefixedComposer, "! B3LYP Opt def2-SVP"),
    ],
)
def test_keyword_block_compose(composer_cls, first_line):
    spec = CalculationSpec.from_kwargs(
        method="DFT",
        method_args={"variant": "B3LYP"},
        module="OPT",
        parameters={
            "BASIS": "def2-SVP",
            "SCF": {
                "MaxIter": 50,
                "KeepInts": True,
                "Shift": {"Shift": 0.1, "ErrOff": 0.1},
            },
        },
        raw=["%output", "  Print[P_Hirshfeld] 1", "end"],
    )
    files = composer_cls().compose(
        spec, load(KEYWORD_BLOCK_DOC), None, ExecutionSpec(cpu=4, ram=2000)
    )
    expected = f"""\
{first_line}
%output
  Print[P_Hirshfeld] 1
end
%scf
  MaxIter 50
  KeepInts true
  Shift
    Shift 0.1
    ErrOff 0.1
  end
end
%pal
  nprocs 4
end
%maxcore 2000
"""
    assert files == {"input.inp": expected}


def test_keyword_block_raw_dict():
    spec = CalculationSpec.from_kwargs(
        method="DFT",
        parameters={"SCF": {"MaxIter": 50}},
        raw={"%SCF": {"TolE": 1e-8}, "%method": {"RunTyp": "Energy"}},
    )
    files = PrefixedComposer().compose(
        spec, load(KEYWORD_BLOCK_DOC), None, ExecutionSpec()
    )
    expected = """\
! SP
%scf
  MaxIter 50
  TolE 1e-08
end
%pal
  nprocs 1
end
%method
  RunTyp Energy
end
"""
    assert files == {"input.inp": expected}


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


@pytest.mark.parametrize("composer_cls", [NamelistComposer, FlatComposer])
def test_composer_not_implemented(schema, composer_cls):
    with pytest.raises(NotImplementedError, match=composer_cls.SYNTAX):
        composer_cls().compose(make_spec(), schema, None, ExecutionSpec())


def test_get_composer_unknown_syntax():
    with pytest.raises(ValueError, match="'API'.*Available: KEYWORD_BLOCK"):
        get_composer("API")


def test_composer_cls_defaults_to_syntax(tmp_path):
    assert NoOverrideSoftware.composer_cls is None
    ctx = make_ctx(tmp_path, make_spec(method="HF", method_args={}))
    NoOverrideSoftware().prepare(ctx)
    assert ctx.input_files == {"input.json": tmp_path / "input.json"}
    expected = """\
Hamiltonian = HF
Driver = SinglePoint
Basis = sto-3g
Resources = {
  Cpu = 2
  Memory = 1000
}
"""
    assert (tmp_path / "input.json").read_text(encoding="utf-8") == expected


def test_composer_cls_override(tmp_path):
    ctx = make_ctx(tmp_path)
    OverrideSoftware().prepare(ctx)
    assert ctx.input_files == {"custom.txt": tmp_path / "custom.txt"}
    assert (tmp_path / "custom.txt").read_text(encoding="utf-8") == "custom\n"


def test_dummy_prepare_writes_deterministic_input(tmp_path):
    spec = make_spec(
        method_args={"variant": "PBE", "Charge": 1},
        module="OPT",
        module_args={"MaxSteps": 10},
        parameters={
            "BASIS": "sto-3g",
            "SCF": {"MaxIter": 50},
            "OUTPUT": {"WriteForces": True},
        },
        raw={"Extra": "keep"},
    )
    contents = []
    for name in ("first", "second"):
        directory = tmp_path / name
        directory.mkdir()
        ctx = make_ctx(directory, spec)
        DummySoftware().prepare(ctx)
        assert ctx.input_files == {"input.json": directory / "input.json"}
        contents.append(ctx.input_files["input.json"].read_text(encoding="utf-8"))
    assert contents[0] == contents[1]
    data = json.loads(contents[0])
    assert contents[0] == json.dumps(data, indent=4, sort_keys=True) + "\n"
    assert data == spec.to_dict()
