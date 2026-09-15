"""Tests of the AMAC calculator with the dummy software."""

import json
import sys
import warnings

import numpy as np
import pytest
from ase import Atoms

import amac
from amac.amac import AMAC
from amac.assets import _dummy
from amac.assets._dummy import inprocess
from amac.assets._dummy.dummy import DummySoftware
from amac.engine import registry
from amac.engine.context import Result
from amac.exceptions import RunError, ValidationError

PYTHON = sys.executable


def water() -> Atoms:
    positions = [[0.0, 0.0, 0.0], [0.76, 0.59, 0.0], [-0.76, 0.59, 0.0]]
    return Atoms("OH2", positions=positions)


def make_calc(tmp_path, **kwargs) -> AMAC:
    arguments = {
        "software": "dummy",
        "method": "DFT",
        "method_args": {"variant": "PBE"},
        "parameters": {"BASIS": "sto-3g"},
        "workdir": tmp_path,
    }
    return AMAC(**arguments | kwargs)


@pytest.fixture
def flaky(monkeypatch):
    """Dummy software failing on 1-atom images and hanging on 2-atom images."""
    monkeypatch.setattr(registry, "_REGISTRY", dict(registry._REGISTRY))

    class FlakySoftware(DummySoftware):
        NAME = "FLAKY_TEST"

        def command(self, ctx):
            if len(ctx.atoms) == 1:
                return [PYTHON, "-c", "import sys; sys.exit(3)"]
            if len(ctx.atoms) == 2:
                return [PYTHON, "-c", "import time; time.sleep(10)"]
            return super().command(ctx)

    return registry.register_software(FlakySoftware)


def test_expectation_scenario_with_dummy(tmp_path):
    image = Atoms(
        ["O", "H", "H", "O", "H", "H"],
        positions=np.array(
            [
                [1.2478, -0.5185, 3.4049],
                [1.5946, -1.4204, 3.3886],
                [0.9008, -0.3341, 2.5062],
                [3.2478, -0.4185, 3.4049],
                [3.5946, -1.5204, 3.3886],
                [2.9008, -0.3341, 2.6062],
            ]
        ),
    )
    calculation_parameters = {
        "method_args": {"variant": "B3LYP"},
        "module_args": {},
        "parameters": {"BASIS": "cc-PVDZ"},
    }
    calculation_argument = {
        "cpu": 2,
        "ram": 4000,
        "workdir": tmp_path / "scratch",
        "outdir": None,
    }
    calc = AMAC(
        software="dummy",
        method="DFT",
        module=None,
        **calculation_argument,
        **calculation_parameters,
    )

    def atom_count(ctx):
        return len(ctx.atoms)

    calc.handler_properties(
        _dummy.energy,
        _dummy.forces,
        atom_count,
        ("positions", lambda ctx: ctx.atoms.get_positions()),
        ("mass", lambda ctx: ctx.atoms.get_masses().sum()),
    )
    result = calc.execute(geometry=image)

    assert isinstance(result, Result)
    assert (result.success, result.errors) == (True, [])
    assert result.properties["energy"] == pytest.approx(-1.0, abs=1e-12)
    assert result.properties["atom_count"] == 6
    assert result.context.directory == tmp_path / "scratch" / "amac"
    assert result.context.driver == "amac"
    assert {"prepare", "run", "collect", "handlers"} <= result.context.timings.keys()

    path = calc.store(filename=tmp_path / "store-dft-dummy", format="json")
    assert path == tmp_path / "store-dft-dummy.json"
    [stored] = amac.load(path)
    assert stored.success is True
    assert stored.properties["forces"] == []
    assert np.array_equal(stored.properties["positions"], image.get_positions())
    assert stored.properties["mass"] == pytest.approx(
        float(image.get_masses().sum()), rel=1e-12
    )
    provenance = stored.provenance
    assert (provenance["software"], provenance["driver"]) == ("DUMMY", "amac")
    assert provenance["spec"] == calc.spec.to_dict()
    assert provenance["exec_spec"]["cpu"] == 2
    assert provenance["duration"] > 0
    assert {"amac_version", "start", "end", "image"} <= provenance.keys()


def test_multiple_images_and_results_replaced(tmp_path):
    calc = make_calc(tmp_path)
    calc.handler_properties(_dummy.energy)
    results = calc.execute([water(), water()])
    assert [result.success for result in results] == [True, True]
    assert [result.context.directory for result in results] == [
        tmp_path / "amac" / "image_000",
        tmp_path / "amac" / "image_001",
    ]
    assert calc.results == results
    single = calc.execute(water(), label="single")
    assert calc.results == [single]
    assert single.context.directory == tmp_path / "single"


def test_raise_on_error_stops_at_failing_image(tmp_path, flaky):
    calc = make_calc(tmp_path, software="flaky_test")
    calc.handler_properties(_dummy.energy)
    with pytest.raises(RunError, match="code 3") as excinfo:
        calc.execute([water(), Atoms("H"), water()])
    assert len(excinfo.value.ctx.atoms) == 1
    assert [result.success for result in calc.results] == [True]


def test_failures_recorded_without_raise_on_error(tmp_path, flaky):
    calc = make_calc(
        tmp_path, software="flaky_test", raise_on_error=False, timeout=0.3
    )
    calc.handler_properties(_dummy.energy)
    images = [water(), Atoms("H"), Atoms("H2", positions=[[0, 0, 0], [0, 0, 0.74]])]
    results = calc.execute([*images, water()])
    assert [result.success for result in results] == [True, False, False, True]
    code_error, timeout_error = results[1].errors[0], results[2].errors[0]
    assert isinstance(code_error, RunError) and "code 3" in str(code_error)
    assert isinstance(timeout_error, RunError) and "timed out" in str(timeout_error)
    assert results[1].properties == results[2].properties == {}
    assert results[2].context.return_code is None
    assert results[3].properties["energy"] == pytest.approx(-1.0, abs=1e-12)


def test_overrides(tmp_path):
    calc = make_calc(tmp_path, cpu=1)
    calc.handler_properties(_dummy.energy)
    result = calc.execute(water(), cpu=4, label="override")
    assert result.context.exec_spec.cpu == 4
    assert result.provenance["exec_spec"]["label"] == "override"
    assert (calc.exec_spec.cpu, calc.exec_spec.label) == (1, None)
    with pytest.raises(TypeError, match="did you mean 'timeout'"):
        calc.execute(water(), timout=1)
    with pytest.raises(TypeError, match="'pbc'"):
        calc.execute(water(), pbc=False)
    with pytest.raises(ValueError, match="driver cannot be overridden"):
        calc.execute(water(), driver="auto")


def test_platform_alias(tmp_path):
    calc = make_calc(tmp_path, software=None, platform="dummy")
    assert calc.software.name == "DUMMY"
    with pytest.raises(TypeError, match="exactly one"):
        make_calc(tmp_path, platform="dummy")
    with pytest.raises(TypeError, match="exactly one"):
        make_calc(tmp_path, software=None)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"timout": 5}, "did you mean 'timeout'"),
        ({"method_arg": {}}, "did you mean 'method_args'"),
        ({"backend": "ORCA"}, "Unknown argument 'backend'"),
        ({"run-delay": None}, "Unknown argument 'run-delay'"),
    ],
)
def test_unknown_arguments(tmp_path, kwargs, match):
    with pytest.raises(TypeError, match=match):
        make_calc(tmp_path, **kwargs)


def test_validation_modes(tmp_path):
    invalid = {"method_args": {"variant": "PBE0"}}
    with pytest.raises(ValidationError, match="variant"):
        make_calc(tmp_path, **invalid)
    with pytest.warns(UserWarning, match="variant"):
        calc = make_calc(tmp_path, validate="warn", **invalid)
    assert [issue.path for issue in calc.issues] == ["method_args.variant"]
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert make_calc(tmp_path, validate="off", **invalid).issues == []
    with pytest.raises(ValueError, match="validation mode"):
        make_calc(tmp_path, validate="lenient")


def test_geometry_validation(tmp_path):
    periodic = Atoms("H", cell=[5.0, 5.0, 5.0], pbc=True)
    molecule_only = {"method_args": {"variant": "B3LYP"}}
    calc = make_calc(tmp_path, **molecule_only)
    with pytest.raises(ValidationError, match="MOLECULE only"):
        calc.execute(periodic)
    assert not (tmp_path / "amac").exists()
    calc = make_calc(tmp_path, validate="warn", **molecule_only)
    calc.handler_properties(_dummy.energy)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert calc.execute(periodic).success
    assert any("MOLECULE only" in str(warning.message) for warning in caught)


@pytest.mark.parametrize(
    ("geometry", "error"),
    [
        ("H2O", TypeError),
        (42, TypeError),
        ([water(), "H2O"], TypeError),
        ([], ValueError),
    ],
    ids=["str", "int", "mixed-list", "empty"],
)
def test_invalid_geometry(tmp_path, geometry, error):
    with pytest.raises(error):
        make_calc(tmp_path).execute(geometry)


def test_handler_properties_replaces_previous_handlers(tmp_path):
    calc = make_calc(tmp_path)
    calc.handler_properties(_dummy.energy)
    calc.handler_properties(_dummy.forces)
    assert [meta.name for meta in calc.handlers] == ["forces"]
    with pytest.raises(ValueError, match="Duplicate result name"):
        calc.handler_properties(_dummy.energy, ("energy", lambda ctx: 0.0))


def test_to_dict_from_dict(tmp_path):
    calc = make_calc(tmp_path, cpu=2, label="calc", validate="warn", driver="auto")
    data = calc.to_dict()
    assert json.loads(json.dumps(data)) == data
    clone = AMAC.from_dict(data)
    assert clone.to_dict() == data
    assert "software='DUMMY'" in repr(clone)
    with pytest.raises(ValueError, match="AMAC data must have the keys"):
        AMAC.from_dict(data | {"unknown": []})


def test_store_formats(tmp_path):
    calc = make_calc(tmp_path)
    path = calc.store(tmp_path / "empty.JSON")
    assert path == tmp_path / "empty.JSON"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "format": "amac-results",
        "format_version": 1,
        "results": [],
    }
    with pytest.raises(NotImplementedError, match="yaml"):
        calc.store(tmp_path / "results", format="yaml")


def test_inprocess_single_and_multiple_images(tmp_path):
    calc = make_calc(tmp_path, software="dummy-inprocess")
    with pytest.raises(ValueError, match="belongs to DUMMY"):
        calc.handler_properties(_dummy.energy)
    calc.handler_properties(inprocess.energy, inprocess.forces)
    single = calc.execute(water())
    expected_energy, expected_forces = inprocess.PairModel().evaluate(water().positions)
    assert (single.success, single.errors) == (True, [])
    assert single.properties["energy"] == pytest.approx(expected_energy, rel=1e-12)
    assert np.array_equal(single.properties["forces"], expected_forces)
    ctx = single.context
    assert ctx.directory == tmp_path / "amac"
    assert ctx.directory.is_dir()
    assert ctx.stdout == "dummy-inprocess: 3 atoms\n"
    assert (ctx.return_code, ctx.files) == (None, {})
    assert {"prepare", "run", "collect", "handlers"} <= ctx.timings.keys()

    results = calc.execute([water(), Atoms("H")], label="images")
    assert [result.context.directory.name for result in results] == [
        "image_000",
        "image_001",
    ]
    assert results[1].properties["energy"] == pytest.approx(0.0, abs=0.0)

    first, second = amac.load(calc.store(tmp_path / "inprocess"))
    assert first.provenance["software"] == "DUMMY_INPROCESS"
    assert np.array_equal(first.properties["forces"], expected_forces)
    assert second.properties["forces"].shape == (1, 3)


def test_inprocess_forces_are_minus_the_gradient():
    model = inprocess.PairModel(stiffness=2.0, bond_length=0.9)
    positions = water().positions
    _, forces = model.evaluate(positions)
    step = 1e-6
    numerical = np.zeros_like(positions)
    for index in np.ndindex(positions.shape):
        plus, minus = positions.copy(), positions.copy()
        plus[index] += step
        minus[index] -= step
        energy_plus = model.evaluate(plus)[0]
        energy_minus = model.evaluate(minus)[0]
        numerical[index] = -(energy_plus - energy_minus) / (2 * step)
    assert forces == pytest.approx(numerical, abs=1e-6)
