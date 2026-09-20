"""Tests of amac.parameter.schema."""

import json
from pathlib import Path

import pytest

import amac
from amac.exceptions import ValidationError
from amac.parameter.schema import REQUIRED_KEYS, load

DFTBPLUS_DOC = Path(amac.__file__).parent / "assets" / "dftbplus" / "doc.json"


def minimal_doc(**sections) -> dict:
    doc = {key: {} for key in REQUIRED_KEYS}
    doc |= {"SOFTWARE": "X", "VERSION": "0", "SYNTAX": "FLAT", "EXECUTION": []}
    return doc | sections


def test_resolve_alias_ambiguous_name(tmp_path):
    modules = {"A": {"ALIASES": ["X"]}, "B": {"ALIASES": ["x"]}}
    path = tmp_path / "doc.json"
    path.write_text(json.dumps(minimal_doc(MODULES=modules)), encoding="utf-8")
    with pytest.raises(ValidationError, match="Ambiguous"):
        load(path).resolve_alias("MODULES", "x")


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
