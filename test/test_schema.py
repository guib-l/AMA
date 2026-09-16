"""Tests of amac.parameter.schema."""

import json
from pathlib import Path

import pytest

import amac
from amac.exceptions import ValidationError
from amac.parameter.schema import REQUIRED_KEYS, Schema, load

DFTBPLUS_DOC = Path(amac.__file__).parent / "assets" / "dftbplus" / "doc.json"
SCHEMA_DOC = Path(__file__).parent / "fixtures" / "schema.json"


def minimal_doc(**sections) -> dict:
    doc = {key: {} for key in REQUIRED_KEYS}
    doc |= {"SOFTWARE": "X", "VERSION": "0", "SYNTAX": "FLAT", "EXECUTION": []}
    return doc | sections


@pytest.fixture
def schema() -> Schema:
    return load(SCHEMA_DOC)


def test_load_exposes_sections(schema):
    assert set(schema.modules) == {"SINGLE_POINT", "GEOMETRY_OPTIMISATION"}
    assert set(schema.methods) == {"HF", "DFT"}
    assert "BASIS" in schema.parameters
    assert "FILES" in schema.output
    assert schema.input["FILENAME"] == "input.json"
    assert schema.syntax == "TREE"
    assert schema.execution == ("FILEIO",)


def test_schema_is_read_only(schema):
    with pytest.raises(TypeError):
        schema.modules["NEW"] = {}


def test_load_is_cached():
    assert load(SCHEMA_DOC) is load(str(SCHEMA_DOC))


@pytest.mark.parametrize(
    ("section", "name", "expected"),
    [
        ("MODULES", "sp", "SINGLE_POINT"),
        ("modules", "Geometry_Optimisation", "GEOMETRY_OPTIMISATION"),
        ("METHODS", "hartree_fock", "HF"),
        ("PARAMETERS", "scf_options", "SCF"),
    ],
)
def test_resolve_alias(schema, section, name, expected):
    assert schema.resolve_alias(section, name) == expected


def test_resolve_alias_unknown_name(schema):
    with pytest.raises(ValidationError, match="Unknown"):
        schema.resolve_alias("MODULES", "MD")


def test_resolve_alias_ambiguous_name(tmp_path):
    modules = {"A": {"ALIASES": ["X"]}, "B": {"ALIASES": ["x"]}}
    path = tmp_path / "doc.json"
    path.write_text(json.dumps(minimal_doc(MODULES=modules)), encoding="utf-8")
    with pytest.raises(ValidationError, match="Ambiguous"):
        load(path).resolve_alias("MODULES", "x")


def test_resolve_alias_unknown_section(schema):
    with pytest.raises(ValueError, match="section"):
        schema.resolve_alias("OUTPUT", "FILES")


@pytest.mark.parametrize(
    ("content", "match"),
    [
        (
            json.dumps({k: v for k, v in minimal_doc().items() if k != "SYNTAX"}),
            "SYNTAX",
        ),
        (json.dumps(minimal_doc(MODULES=[])), "MODULES"),
        (json.dumps([]), "JSON object"),
        ("{not json", "not valid JSON"),
    ],
    ids=["missing-key", "section-not-object", "not-object", "invalid-json"],
)
def test_load_non_conforming_doc(tmp_path, content, match):
    path = tmp_path / "doc.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValidationError, match=match):
        load(path)


def test_load_dftbplus_doc():
    schema = load(DFTBPLUS_DOC)
    assert schema.syntax == "TREE"
    assert schema.resolve_alias("MODULES", "opt") == "GEOMETRY_OPTIMISATION"
