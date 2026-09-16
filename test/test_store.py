"""Tests of amac.ios.store: store → load round trip and provenance."""

import json
import socket
import sys
from datetime import datetime, timedelta

import numpy as np
import pytest
from ase import Atoms

import amac
from amac import AMAC
from amac.assets import _dummy
from amac.assets._dummy.dummy import DummySoftware
from amac.engine import registry
from amac.engine.context import Result
from amac.engine.handlers import handler
from amac.ios.store import FORMAT, FORMAT_VERSION, load_results, store_results

PYTHON = sys.executable

PROVENANCE_KEYS = {
    "amac_version",
    "software",
    "software_version",
    "driver",
    "driver_version",
    "driver_fallback",
    "image",
    "spec",
    "exec_spec",
    "validated",
    "reprocessed",
    "directory",
    "outdir",
    "hostname",
    "start",
    "end",
    "duration",
    "atoms",
}


def water() -> Atoms:
    positions = [[0.0, 0.0, 0.0], [0.76, 0.59, 0.0], [-0.76, 0.59, 0.0]]
    return Atoms("OH2", positions=positions)


def make_calc(tmp_path, **kwargs) -> AMAC:
    arguments = {
        "software": "dummy",
        "validate": "off",
        "method": "DFT",
        "method_args": {"variant": "PBE"},
        "parameters": {"BASIS": "sto-3g"},
        "workdir": tmp_path / "work",
    }
    calc = AMAC(**arguments | kwargs)
    calc.handler_properties(_dummy.energy)
    return calc


@pytest.fixture
def isolated_registry(monkeypatch):
    """Let a test register software without leaking it into the global registry."""
    monkeypatch.setattr(registry, "_REGISTRY", dict(registry._REGISTRY))
    return registry.register_software


def test_properties_round_trip(tmp_path):
    properties = {
        "float_array": np.arange(6, dtype=np.float64).reshape(2, 3) / 3,
        "int_array": np.array([[1, 2], [3, 4]], dtype=np.int32),
        "empty_array": np.zeros((0, 3)),
        "bool_scalar": np.bool_(True),
        "float_scalar": np.float32(0.5),
        "int_scalar": np.int64(7),
        "list": [1, 2.5, "a", None, (3, 4)],
        "nested": {"a": {"b": [np.float64(1.25), {"c": np.array([True, False])}]}},
        "path": tmp_path / "file.txt",
        "atoms": water(),
    }
    path = store_results([Result(True, properties)], tmp_path / "properties")
    [loaded] = load_results(path)
    restored = loaded.properties

    for name in ("float_array", "int_array", "empty_array"):
        assert np.array_equal(restored[name], properties[name])
        assert restored[name].dtype == properties[name].dtype
        assert restored[name].shape == properties[name].shape
    assert restored["bool_scalar"] is True
    assert type(restored["float_scalar"]) is float
    assert restored["float_scalar"] == pytest.approx(0.5, abs=0.0)
    assert (type(restored["int_scalar"]), restored["int_scalar"]) == (int, 7)
    assert restored["list"] == [1, 2.5, "a", None, [3, 4]]
    first, second = restored["nested"]["a"]["b"]
    assert first == pytest.approx(1.25, abs=0.0)
    assert np.array_equal(second["c"], [True, False])
    assert second["c"].dtype == np.bool_
    assert restored["path"] == str(tmp_path / "file.txt")
    assert isinstance(restored["atoms"], Atoms)
    assert restored["atoms"].get_chemical_symbols() == ["O", "H", "H"]
    assert np.array_equal(restored["atoms"].positions, properties["atoms"].positions)
    assert (loaded.success, loaded.errors, loaded.context) == (True, [], None)


def test_geometry_restored(tmp_path):
    atoms = Atoms(
        "H2",
        positions=[[0.1, 0.2, 0.3], [0.1, 0.2, 1.04]],
        cell=[[4.0, 0.0, 0.0], [0.0, 5.0, 0.0], [0.0, 0.0, 6.0]],
        pbc=[True, False, True],
    )
    atoms.set_initial_charges([0.5, -0.5])
    atoms.set_initial_magnetic_moments([1.0, 0.0])
    atoms.info["note"] = "not stored"
    calc = make_calc(tmp_path)
    calc.execute([atoms, water()])
    path = calc.store(tmp_path / "geometry")

    charged, neutral = (result.provenance["atoms"] for result in amac.load(path))
    assert charged.get_chemical_symbols() == ["H", "H"]
    assert np.array_equal(charged.positions, atoms.positions)
    assert np.array_equal(charged.cell.array, atoms.cell.array)
    assert charged.pbc.tolist() == [True, False, True]
    assert np.array_equal(charged.get_initial_charges(), [0.5, -0.5])
    assert np.array_equal(charged.get_initial_magnetic_moments(), [1.0, 0.0])
    assert charged.info == {}
    assert not neutral.has("initial_charges")
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert set(raw["results"][1]["provenance"]["atoms"]) == {
        "symbols",
        "positions",
        "cell",
        "pbc",
    }


def test_provenance_complete(tmp_path):
    env = {"API_TOKEN": "secret-value", "OMP_NUM_THREADS": "1"}
    calc = make_calc(tmp_path, driver="auto", env=env, cpu=2)
    result = calc.execute(water())
    path = calc.store(tmp_path / "provenance")
    assert "secret-value" not in path.read_text(encoding="utf-8")

    [loaded] = amac.load(path)
    provenance = loaded.provenance
    assert set(provenance) == PROVENANCE_KEYS
    assert provenance["amac_version"] == amac.__version__
    assert (provenance["software"], provenance["software_version"]) == ("DUMMY", None)
    assert (provenance["driver"], provenance["driver_version"]) == ("amac", None)
    assert provenance["driver_fallback"].startswith("dummy-lib: missing")
    assert provenance["image"] is None
    assert provenance["spec"] == calc.spec.to_dict()
    assert provenance["exec_spec"]["cpu"] == 2
    masked = {"API_TOKEN": "***", "OMP_NUM_THREADS": "***"}
    assert provenance["exec_spec"]["env"] == masked
    assert result.provenance["exec_spec"]["env"] == provenance["exec_spec"]["env"]
    assert calc.exec_spec.env == env
    assert provenance["hostname"] == socket.gethostname()
    start = datetime.fromisoformat(provenance["start"])
    end = datetime.fromisoformat(provenance["end"])
    assert start.utcoffset() == end.utcoffset() == timedelta(0)
    assert start <= end
    assert provenance["duration"] > 0
    assert isinstance(provenance["atoms"], Atoms)


def test_software_version_failure_gives_none(tmp_path, isolated_registry):
    class BrokenVersionSoftware(DummySoftware):
        NAME = "BROKEN_VERSION_TEST"
        calls = 0

        def version(self):
            type(self).calls += 1
            raise RuntimeError("no version")

    isolated_registry(BrokenVersionSoftware)
    calc = make_calc(tmp_path, software="broken_version_test")
    results = calc.execute([water(), water()])
    assert [result.success for result in results] == [True, True]
    assert [result.provenance["software_version"] for result in results] == [None, None]
    assert BrokenVersionSoftware.calls == 1


def test_errors_restored_as_dicts(tmp_path, isolated_registry):
    class OneAtomFailure(DummySoftware):
        NAME = "ONE_ATOM_FAILURE_TEST"

        def command(self, ctx):
            if len(ctx.atoms) == 1:
                return [PYTHON, "-c", "import sys; sys.exit(3)"]
            return super().command(ctx)

    isolated_registry(OneAtomFailure)

    @handler(software="one_atom_failure_test", requires_files=("missing.dat",))
    def needs_missing(ctx):
        return None

    calc = make_calc(tmp_path, software="one_atom_failure_test", raise_on_error=False)
    calc.handler_properties(_dummy.energy, ("broken", lambda ctx: 1 / 0), needs_missing)
    results = calc.execute([water(), Atoms("H")])
    first, second = amac.load(calc.store(tmp_path / "errors"))

    assert (first.success, second.success) == (True, False)
    assert first.properties["energy"] == pytest.approx(-1.0, abs=1e-12)
    assert first.errors == [
        {
            "type": "HandlerError",
            "message": str(results[0].errors[0]),
            "handler": "broken",
        },
        {
            "type": "HandlerError",
            "message": str(results[0].errors[1]),
            "handler": "needs_missing",
            "missing_files": ["missing.dat"],
        },
    ]
    assert second.errors == [
        {"type": "RunError", "message": str(results[1].errors[0])}
    ]
    assert [first.provenance["image"], second.provenance["image"]] == [0, 1]
    assert [len(first.provenance["atoms"]), len(second.provenance["atoms"])] == [3, 1]


@pytest.mark.parametrize(
    "value",
    [
        object(),
        1 + 2j,
        np.array([1j]),
        np.complex128(1j),
        {1: "int key"},
        {"__ndarray__": "reserved"},
    ],
    ids=["object", "complex", "complex-array", "numpy-complex", "int-key", "tag"],
)
def test_unserializable_value(tmp_path, value):
    with pytest.raises(TypeError):
        store_results([Result(True, {"value": value})], tmp_path / "bad")
    assert not (tmp_path / "bad.json").exists()


@pytest.mark.parametrize(
    ("content", "match"),
    [
        (json.dumps({"results": []}), "not an AMAC results file"),
        (json.dumps([]), "not an AMAC results file"),
        (
            json.dumps({"format": FORMAT, "format_version": 99, "results": []}),
            "unsupported format_version 99",
        ),
        ("{not json", "not valid JSON"),
    ],
    ids=["no-header", "not-object", "unknown-version", "invalid-json"],
)
def test_load_rejects_invalid_files(tmp_path, content, match):
    path = tmp_path / "invalid.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=match):
        load_results(path)


def test_header_and_json_suffix(tmp_path):
    path = store_results([], tmp_path / "results")
    assert path == tmp_path / "results.json"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "results": [],
    }
    assert amac.load(tmp_path / "results") == []


def test_unsupported_format(tmp_path):
    with pytest.raises(NotImplementedError, match="'yaml'"):
        store_results([], tmp_path / "results", format="yaml")
