"""Tests of amac.parameter.catalog and of the CANONICAL links of the doc.json files."""

import json
from pathlib import Path
from typing import Any

import pytest

from amac.exceptions import ValidationError
from amac.parameter.catalog import (
    CATALOG_DIR,
    KINDS,
    Catalog,
    documented_software,
    links,
    load_catalog,
)
from amac.parameter.schema import REQUIRED_KEYS, load, resolve_name


@pytest.fixture
def catalog() -> Catalog:
    return load_catalog()


def write_entry(root: Path, kind_dir: str, slug: str, content: Any) -> Path:
    path = root / kind_dir / slug / "entry.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(content), encoding="utf-8")
    return path


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
    assert (b3lyp.kind, b3lyp.parent, b3lyp.source) == ("METHOD", "DFT", "methods/dft")
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


def test_catalog_tree_order_and_source(tmp_path):
    write_entry(tmp_path, "options", "dispersion", {"ID": "DISPERSION"})
    write_entry(tmp_path, "methods", "hf", {"ID": "HF"})
    write_entry(
        tmp_path, "methods", "dft", {"ID": "DFT", "VARIANTS": {"PBE": {}, "B3LYP": {}}}
    )
    (tmp_path / "README.md").write_text("root", encoding="utf-8")
    (tmp_path / "methods" / "README.md").write_text("kind", encoding="utf-8")
    (tmp_path / "methods" / "dft" / "README.md").write_text("slug", encoding="utf-8")
    entries = load_catalog(tmp_path).entries
    assert list(entries) == ["DFT", "PBE", "B3LYP", "HF", "DISPERSION"]
    assert (entries["PBE"].parent, entries["PBE"].source) == ("DFT", "methods/dft")
    assert "ID" not in entries["DFT"].data


@pytest.mark.parametrize(
    ("files", "message"),
    [
        (
            [("methods", "a", {"ID": "HF"}), ("methods", "b", {"ID": "HF"})],
            "HF is already declared in methods/a/entry.json",
        ),
        (
            [
                ("methods", "hf", {"ID": "HF", "ALIASES": ["pbe"]}),
                ("methods", "dft", {"ID": "DFT", "VARIANTS": {"PBE": {}}}),
            ],
            "name 'pbe' of HF is already used by PBE",
        ),
        (
            [("methods", "hf", {"ID": "HF", "ACCEPTS": ["DISPERSION"]})],
            "ACCEPTS 'DISPERSION', which is not an option axis",
        ),
        (
            [("methods", "dft", {"ID": "DFT", "VARIANT_REQUIRED": True})],
            "DFT requires a variant but has none",
        ),
        (
            [("methods", "hf", {"ID": "HF", "ALIASES": "RHF"})],
            "ALIASES must be a list",
        ),
        ([("methods", "hf", ["HF"])], "the top level must be a JSON object"),
        ([("methods", "hf", {"ALIASES": ["RHF"]})], "ID must be a non-empty str"),
        ([("methods", "hf", {"ID": ""})], "ID must be a non-empty str"),
        ([("methods", "hf", {"ID": 1})], "ID must be a non-empty str"),
        (
            [("methods", "dft", {"ID": "DFT", "VARIANTS": {"PBE": {"ID": "PBE"}}})],
            "PBE: ID is only allowed at the top level",
        ),
        ([("methods", "Hf", {"ID": "HF"})], "invalid slug"),
        ([("methods", "hartree_fock", {"ID": "HF"})], "invalid slug"),
        ([("methods", "hf-", {"ID": "HF"})], "invalid slug"),
        (
            [("functionals", "b3lyp", {"ID": "B3LYP"})],
            "functionals: not a catalog kind directory",
        ),
    ],
)
def test_invalid_catalog(tmp_path, files, message):
    for kind_dir, slug, content in files:
        write_entry(tmp_path, kind_dir, slug, content)
    with pytest.raises(ValidationError, match=message):
        load_catalog(tmp_path)


def test_catalog_slug_without_entry(tmp_path):
    write_entry(tmp_path, "methods", "hf", {"ID": "HF"})
    (tmp_path / "methods" / "dft").mkdir()
    with pytest.raises(ValidationError, match="dft: missing entry.json"):
        load_catalog(tmp_path)


def test_catalog_without_file(tmp_path):
    (tmp_path / "methods").mkdir()
    (tmp_path / "README.md").write_text("catalog", encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        load_catalog(tmp_path)


def test_catalog_invalid_json(tmp_path):
    path = tmp_path / "methods" / "hf" / "entry.json"
    path.parent.mkdir(parents=True)
    path.write_text("{", encoding="utf-8")
    with pytest.raises(ValidationError, match="not valid JSON"):
        load_catalog(tmp_path)


# ---------------------------------------------------------------------------
# CANONICAL links


def test_dftbplus_links(tmp_path):
    damping = {"TYPE": "CHOICE", "VALUES": ["BeckeJohnson", "ZeroDamping"]}
    sections = {
        "SOFTWARE": "DFTBP",
        "MODULES": {
            "SECOND_DERIVATIVES": {
                "KEYWORD": "SecondDerivatives",
                "CANONICAL": "HESSIAN",
            },
            "MODES": {"CANONICAL": {"FREQUENCIES": {"EQUIVALENCE": "APPROX"}}},
        },
        "METHODS": {
            "TIGHT_BINDING": {
                "KEYWORD": "DFTB",
                "CANONICAL": "DFTB",
                "VARIANTS": {"DFTB2": {"CANONICAL": "DFTB2"}},
            }
        },
        "PARAMETERS": {
            "DISPERSION": {
                "ARGUMENTS": {
                    "DftD3": {
                        "ARGUMENTS": {"Damping": damping},
                        "CANONICAL": {"D3(BJ)": {"SETS": {"Damping": "BeckeJohnson"}}},
                    },
                    "SimpleDftD3": {"CANONICAL": {"D3(BJ)": {"NOTE": "Internal."}}},
                }
            }
        },
    }
    schema = load(write_doc(tmp_path, **sections))
    (dftb2,) = links_to(schema, "DFTB2")
    assert dftb2.software == "DFTBP"
    assert dftb2.location == ("METHODS", "TIGHT_BINDING", "VARIANTS", "DFTB2")
    assert (dftb2.keyword, dftb2.equivalence, dftb2.note) == ("DFTB2", "EXACT", None)
    (hessian,) = links_to(schema, "HESSIAN")
    assert hessian.keyword == "SecondDerivatives"
    d3bj = links_to(schema, "D3(BJ)")
    assert [link.keyword for link in d3bj] == ["DftD3", "SimpleDftD3"]
    assert dict(d3bj[0].sets) == {"Damping": "BeckeJohnson"}
    assert (d3bj[0].note, d3bj[1].note) == (None, "Internal.")
    (modes,) = links_to(schema, "FREQUENCIES")
    assert modes.equivalence == "APPROX"


def test_every_documented_software_links_resolve():
    for schema in documented_software().values():
        assert links(schema)


# A canonical name realised by two different nodes of the same software: no alias
# can tell them apart, so the user names the node of the software instead.
AMBIGUOUS_LINKS = {("DFTBP", "D3(BJ)")}


def _container(schema, location: tuple[str, ...]) -> Any:
    """Return the mapping the node of ``location`` is a key of."""
    node = schema.data
    for part in location[:-1]:
        node = node[part]
    return node


def test_canonical_names_are_accepted_by_their_software():
    """A catalog name must be usable in a spec, where the node it names lives.

    The catalog is not read when a spec is resolved: a ``doc.json`` accepts a
    canonical name only because its node carries it as a key or an alias. This
    test is what keeps the two in step, and fails when a ``CANONICAL`` is added
    without the matching alias.
    """
    unreachable = []
    for name, schema in documented_software().items():
        for link in links(schema):
            if (name, link.canonical) in AMBIGUOUS_LINKS:
                continue
            try:
                resolve_name(_container(schema, link.location), link.canonical)
            except ValidationError:
                unreachable.append(
                    f"{name}: '{link.canonical}' names {'/'.join(link.location)}, "
                    f"which answers to '{link.location[-1]}' only"
                )
    assert not unreachable, "\n".join(unreachable)


@pytest.mark.parametrize(("software", "canonical"), sorted(AMBIGUOUS_LINKS))
def test_ambiguous_canonical_names_stay_ambiguous(software, canonical):
    """The known exceptions are real: several nodes realise the same name."""
    schema = documented_software()[software]
    realising = [link for link in links(schema) if link.canonical == canonical]
    assert len(realising) > 1


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


def test_documented_software_skips_private_modules():
    schemas = documented_software()
    assert "DFTBP" in schemas
    assert not {"DUMMY", "DUMMY_INPROCESS"} & schemas.keys()
