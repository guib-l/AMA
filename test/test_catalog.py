"""Tests of amac.parameter.catalog and of the CANONICAL links of the doc.json files."""

import json
from pathlib import Path

import pytest

import amac
from amac.assets.catalog.__main__ import main
from amac.exceptions import ValidationError
from amac.parameter.catalog import (
    CATALOG_DIR,
    KINDS,
    OUTPUT_FILES,
    Catalog,
    availability,
    availability_document,
    available,
    documented_software,
    links,
    load_catalog,
    write_availability,
)
from amac.parameter.schema import REQUIRED_KEYS, load

ROOT = Path(__file__).resolve().parents[1]
DFTBPLUS_DOC = Path(amac.__file__).parent / "assets" / "dftbplus" / "doc.json"


@pytest.fixture
def catalog() -> Catalog:
    return load_catalog()


@pytest.fixture
def dftbplus():
    return load(DFTBPLUS_DOC)


def catalog_file(kind: str, entries: dict, **extra) -> dict:
    return {"CATALOG": kind, "KIND": kind, "ENTRIES": entries} | extra


def write_doc(directory: Path, **sections) -> Path:
    doc = {key: {} for key in REQUIRED_KEYS}
    doc |= {"SOFTWARE": "X", "VERSION": "0", "SYNTAX": "FLAT", "EXECUTION": []}
    path = directory / "doc.json"
    path.write_text(json.dumps(doc | sections), encoding="utf-8")
    return path


def links_to(schema, canonical: str) -> list:
    return [link for link in links(schema) if link.canonical == canonical]


# ---------------------------------------------------------------------------
# Catalog


def test_catalog_entries(catalog):
    b3lyp = catalog.entries["B3LYP"]
    assert (b3lyp.kind, b3lyp.parent, b3lyp.source) == ("METHOD", "DFT", "functionals")
    assert catalog.entries["DFTB2"].parent == "DFTB"
    assert catalog.entries["D3(BJ)"].kind == "OPTION"
    assert catalog.entries["DISPERSION"].parent is None
    assert catalog.entries["M06-2X"].aliases == ("M062X",)


def test_catalog_is_cached_and_read_only(catalog):
    assert load_catalog(str(CATALOG_DIR)) is catalog
    with pytest.raises(TypeError):
        catalog.entries["NEW"] = None
    with pytest.raises(TypeError):
        catalog.entries["HF"].data["ALIASES"] = ()


@pytest.mark.parametrize(
    ("name", "kind", "expected"),
    [
        ("m062x", None, "M06-2X"),
        ("SCC-DFTB", "METHOD", "DFTB2"),
        ("d3bj", "OPTION", "D3(BJ)"),
        ("freq", "MODULE", "FREQUENCIES"),
        ("uks", None, "UNRESTRICTED"),
    ],
)
def test_resolve(catalog, name, kind, expected):
    assert catalog.resolve(name, kind).id == expected


def test_resolve_errors(catalog):
    with pytest.raises(ValidationError, match="Unknown catalog METHOD 'FREQ'"):
        catalog.resolve("FREQ", kind="METHOD")
    with pytest.raises(ValueError, match="Unknown kind"):
        catalog.resolve("HF", kind="FUNCTIONAL")


def test_children_and_kinds(catalog):
    assert {"B3LYP", "PBE0"} <= {entry.id for entry in catalog.children("DFT")}
    assert "D4" in {entry.id for entry in catalog.children("DISPERSION")}
    assert catalog.children("HF") == ()
    assert all(entry.kind == "MODULE" for entry in catalog.of_kind("MODULE"))
    assert sum(len(catalog.of_kind(kind)) for kind in KINDS) == len(catalog.entries)
    with pytest.raises(KeyError):
        catalog.children("NOPE")


@pytest.mark.parametrize(
    ("files", "message"),
    [
        (
            {
                "a": catalog_file("METHOD", {"HF": {}}),
                "b": catalog_file("METHOD", {"HF": {}}),
            },
            "HF is already declared in a.json",
        ),
        (
            {"a": catalog_file("METHOD", {"HF": {"ALIASES": ["pbe"]}, "DFT": {"VARIANTS": {"PBE": {}}}})},
            "name 'PBE' of PBE is already used by HF",
        ),
        (
            {"a": catalog_file("METHOD", {"B3LYP": {}}, PARENT="DFT")},
            "PARENT 'DFT' is not a METHOD entry",
        ),
        (
            {"a": catalog_file("METHOD", {"HF": {"ACCEPTS": ["DISPERSION"]}})},
            "ACCEPTS 'DISPERSION', which is not an option axis",
        ),
        (
            {"a": catalog_file("METHOD", {"DFT": {"VARIANT_REQUIRED": True}})},
            "DFT requires a variant but has none",
        ),
        ({"a": catalog_file("FUNCTIONAL", {})}, "KIND must be one of"),
        (
            {"a": catalog_file("METHOD", {"HF": {"ALIASES": "RHF"}})},
            "ALIASES must be a list",
        ),
        ({"a": {"KIND": "METHOD", "ENTRIES": {}}}, "missing top-level keys: CATALOG"),
    ],
)
def test_invalid_catalog(tmp_path, files, message):
    for stem, content in files.items():
        (tmp_path / f"{stem}.json").write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ValidationError, match=message):
        load_catalog(tmp_path)


def test_catalog_without_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_catalog(tmp_path)


def test_catalog_invalid_json(tmp_path):
    (tmp_path / "a.json").write_text("{", encoding="utf-8")
    with pytest.raises(ValidationError, match="not valid JSON"):
        load_catalog(tmp_path)


# ---------------------------------------------------------------------------
# CANONICAL links


def test_dftbplus_links(dftbplus):
    (dftb2,) = links_to(dftbplus, "DFTB2")
    assert dftb2.software == "DFTBP"
    assert dftb2.location == ("METHODS", "TIGHT_BINDING", "VARIANTS", "DFTB2")
    assert (dftb2.keyword, dftb2.equivalence, dftb2.note) == ("DFTB2", "EXACT", None)
    (hessian,) = links_to(dftbplus, "HESSIAN")
    assert hessian.keyword == "SecondDerivatives"
    d3bj = links_to(dftbplus, "D3(BJ)")
    assert [link.keyword for link in d3bj] == ["DftD3", "SimpleDftD3"]
    assert dict(d3bj[0].sets) == {"Damping": "BeckeJohnson"}
    assert d3bj[1].note
    (modes,) = links_to(dftbplus, "FREQUENCIES")
    assert modes.equivalence == "APPROX"


def test_every_documented_software_links_resolve():
    for schema in documented_software().values():
        assert links(schema)


def test_nested_link(tmp_path):
    field = {
        "ARGUMENTS": {
            "Ext": {
                "KEYWORD": "External",
                "CANONICAL": {"ELECTRIC_FIELD": {"EQUIVALENCE": "APPROX", "NOTE": "n"}},
            }
        }
    }
    (link,) = links(load(write_doc(tmp_path, PARAMETERS={"FIELD": field})))
    assert link.location == ("PARAMETERS", "FIELD", "ARGUMENTS", "Ext")
    assert (link.keyword, link.equivalence, link.note) == ("External", "APPROX", "n")
    assert dict(link.sets) == {}


@pytest.mark.parametrize(
    ("sections", "message"),
    [
        ({"METHODS": {"X": {"CANONICAL": "NOPE"}}}, "unknown catalog id 'NOPE'"),
        (
            {"METHODS": {"X": {"CANONICAL": "scc-dftb"}}},
            "use the catalog id 'DFTB2', not 'scc-dftb'",
        ),
        (
            {"METHODS": {"X": {"CANONICAL": "SINGLE_POINT"}}},
            "MODULE 'SINGLE_POINT' cannot be linked from METHODS",
        ),
        (
            {"MODULES": {"X": {"CANONICAL": "HF"}}},
            "METHOD 'HF' cannot be linked from MODULES",
        ),
        (
            {"METHODS": {"X": {"CANONICAL": ["HF"]}}},
            "CANONICAL must be a catalog id or a non-empty object",
        ),
        (
            {"METHODS": {"X": {"CANONICAL": {"HF": {"EQUIVALENCE": "CLOSE"}}}}},
            "EQUIVALENCE must be one of",
        ),
        (
            {"METHODS": {"X": {"CANONICAL": {"HF": {"WHY": 1}}}}},
            "unknown keys in CANONICAL 'HF': WHY",
        ),
        (
            {"PARAMETERS": {"X": {"CANONICAL": {"D4": {"SETS": {"s6": 1.0}}}}}},
            "Unknown SETS option 's6'",
        ),
        (
            {
                "PARAMETERS": {
                    "X": {
                        "ARGUMENTS": {"Damping": {"TYPE": "CHOICE", "VALUES": ["Zero"]}},
                        "CANONICAL": {"D3(BJ)": {"SETS": {"damping": "BJ"}}},
                    }
                }
            },
            "SETS gives Damping the value 'BJ'",
        ),
    ],
)
def test_invalid_links(tmp_path, sections, message):
    schema = load(write_doc(tmp_path, **sections))
    with pytest.raises(ValidationError, match=message):
        links(schema)


# ---------------------------------------------------------------------------
# Availability


def test_documented_software_skips_private_modules():
    schemas = documented_software()
    assert "DFTBP" in schemas
    assert not {"DUMMY", "DUMMY_INPROCESS"} & schemas.keys()


def test_availability(dftbplus, catalog):
    table = availability("METHOD", {"DFTBP": dftbplus})
    assert [link.keyword for link in table["DFTB2"]["DFTBP"]] == ["DFTB2"]
    assert table["B3LYP"] == {"DFTBP": ()}
    assert list(table) == [entry.id for entry in catalog.of_kind("METHOD")]
    with pytest.raises(ValueError, match="Unknown kind"):
        availability("FUNCTIONAL", {})


def test_available_accepts_aliases(dftbplus):
    schemas = {"DFTBP": dftbplus}
    (link,) = available("td-dftb", schemas)["DFTBP"]
    assert link.keyword == "Casida"
    assert available("ccsd(t)", schemas) == {"DFTBP": ()}
    assert amac.available is available


def test_availability_document(dftbplus):
    document = availability_document("OPTION", {"DFTBP": dftbplus})
    assert document["SOFTWARE"] == {"DFTBP": "25.1"}
    d3 = document["ENTRIES"]["D3(0)"]
    assert d3["PARENT"] == "DISPERSION"
    assert d3["SOFTWARE"]["DFTBP"] == [
        {
            "LOCATION": "PARAMETERS/DISPERSION/ARGUMENTS/DftD3",
            "KEYWORD": "DftD3",
            "EQUIVALENCE": "EXACT",
            "SETS": {"Damping": "ZeroDamping"},
        }
    ]
    assert document["ENTRIES"]["PCM"]["SOFTWARE"] == {"DFTBP": None}


@pytest.mark.parametrize("kind", KINDS)
def test_generated_files_are_up_to_date(kind):
    written = json.loads((ROOT / OUTPUT_FILES[kind]).read_text(encoding="utf-8"))
    assert written == availability_document(kind), "run: python -m amac.assets.catalog"


def test_write_availability(tmp_path, dftbplus):
    paths = write_availability(tmp_path, {"DFTBP": dftbplus})
    assert [path.name for path in paths] == list(OUTPUT_FILES.values())
    assert json.loads(paths[0].read_text(encoding="utf-8"))["KIND"] == "METHOD"


def test_command_line(tmp_path, capsys):
    main([str(tmp_path)])
    printed = capsys.readouterr().out.split()
    assert printed == [str(tmp_path / name) for name in OUTPUT_FILES.values()]
