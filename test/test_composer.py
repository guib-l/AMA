"""Tests of amac.parameter.composer on the dummy doc.json."""

import json
from pathlib import Path

import pytest

from amac.assets._dummy.dummy import DummyComposer, DummySoftware
from amac.engine.context import RunContext
from amac.engine.software import FileIOSoftware
from amac.parameter.composer import (
    Composer,
    FlatComposer,
    KeywordBlockComposer,
    NamelistComposer,
    TreeComposer,
    get_composer,
    inject_resources,
    render_bool,
    render_unit,
    translate,
)
from amac.parameter.parameters import CalculationSpec, ExecutionSpec
from amac.parameter.schema import Schema, load


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


def dummy_doc() -> dict:
    return json.loads(DummySoftware.DOC.read_text(encoding="utf-8"))


def write_schema(tmp_path: Path, doc: dict) -> Schema:
    path = tmp_path / "doc.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    return load(path)


def make_ctx(directory: Path, spec: CalculationSpec | None = None) -> RunContext:
    exec_spec = ExecutionSpec(cpu=2, ram=1000)
    return RunContext(None, spec or make_spec(), exec_spec, directory)


class NoOverrideSoftware(FileIOSoftware):
    DOC = DummySoftware.DOC

    def command(self, ctx):
        return []


class StaticComposer(Composer):
    def compose(self, spec, schema, atoms, exec_spec):
        return {"custom.txt": "custom\n"}


class OverrideSoftware(NoOverrideSoftware):
    composer_cls = StaticComposer


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


@pytest.mark.parametrize(
    ("syntax", "composer_cls"),
    [
        ("KEYWORD_BLOCK", KeywordBlockComposer),
        ("TREE", TreeComposer),
        ("namelist", NamelistComposer),
        ("FLAT", FlatComposer),
    ],
)
def test_get_composer_not_implemented(schema, syntax, composer_cls):
    assert get_composer(syntax) is composer_cls
    with pytest.raises(NotImplementedError, match=syntax.upper()):
        composer_cls().compose(make_spec(), schema, None, ExecutionSpec())


def test_get_composer_unknown_syntax():
    with pytest.raises(ValueError, match="'API'.*Available: KEYWORD_BLOCK"):
        get_composer("API")


def test_composer_cls_defaults_to_syntax(tmp_path):
    assert NoOverrideSoftware.composer_cls is None
    with pytest.raises(NotImplementedError, match="TREE"):
        NoOverrideSoftware().prepare(make_ctx(tmp_path))


def test_composer_cls_override(tmp_path):
    assert DummySoftware.composer_cls is DummyComposer
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
    nodes = data["nodes"]
    assert nodes["Hamiltonian"]["value"] == "DFT"
    assert nodes["Hamiltonian"]["children"]["DFT"]["children"]["Charge"]["value"] == 1
    driver = nodes["Driver"]
    assert driver["value"] == "Optimisation"
    assert driver["children"]["Optimisation"]["children"]["MaxSteps"]["value"] == 10
    assert nodes["Scf"]["children"]["MaxIter"]["value"] == 50
    assert nodes["Output"]["children"]["WriteForces"]["value"] is True
    assert nodes["Resources"]["children"]["Cpu"]["value"] == 2
    assert nodes["Resources"]["children"]["Memory"]["value"] == 1000
    assert data["keywords"] == ["PBE"]
    assert data["raw"] == {"Extra": "keep"}
