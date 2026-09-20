"""Tests of the AMAC calculator, on the DFTB+ asset driven by the stub program.

The in-process path (``InProcessSoftware``) goes through the same ``AMAC.execute``;
it is exercised on deMonNano in ``test/assets/test_demonnano_software.py``.
"""

import json
import logging
import shutil
import warnings
from pathlib import Path

import numpy as np
import pytest
from ase import Atoms
from ase.units import Hartree
from conftest import STUB_ENERGY, stub_charges

import amac
from amac.amac import AMAC
from amac.assets import dftbplus
from amac.assets.dftbplus.dftbplus import DftbPlus
from amac.assets.dftbplus.parser import DETAILED_OUT
from amac.engine.context import Result
from amac.engine.handlers import handler
from amac.exceptions import ConfigurationError, RunError, ValidationError


def water() -> Atoms:
    positions = [[0.0, 0.0, 0.0], [0.76, 0.59, 0.0], [-0.76, 0.59, 0.0]]
    return Atoms("OH2", positions=positions)


def atom_count(ctx) -> int:
    """Module-level custom handler, importable as ``<module>:atom_count``."""
    return len(ctx.atoms)


@handler(requires_files=(DETAILED_OUT,))
def output_size(ctx) -> int:
    """Custom handler with requires_files, attached to no software."""
    return ctx.files[DETAILED_OUT].stat().st_size

@pytest.fixture
def no_doc_calc(no_doc_software, tmp_path):
    """Return a factory of calculators on the software without ``doc.json``."""

    def make(**kwargs):
        arguments = {
            "software": "NO_DOC_TEST",
            "method": "DFT",
            "method_args": {"variant": "PBE"},
            "parameters": {"BASIS": "sto-3g"},
            "workdir": tmp_path,
        }
        return AMAC(**arguments | kwargs)

    return make


def test_expectation_scenario(tmp_path, stub_calc):
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
    calc = stub_calc(
        cpu=2, ram=4000, workdir=tmp_path / "scratch", outdir=None, label=None
    )

    def atom_count(ctx):
        return len(ctx.atoms)

    calc.handler_properties(
        dftbplus.energy,
        dftbplus.forces,
        atom_count,
        ("positions", lambda ctx: ctx.atoms.get_positions()),
        ("mass", lambda ctx: ctx.atoms.get_masses().sum()),
    )
    result = calc.execute(geometry=image)

    assert isinstance(result, Result)
    assert (result.success, result.errors) == (True, [])
    assert result.properties["energy"] == pytest.approx(STUB_ENERGY * Hartree)
    assert result.properties["atom_count"] == 6
    assert result.context.directory == tmp_path / "scratch" / "amac"
    assert result.context.driver == "amac"
    assert {"prepare", "run", "collect", "handlers"} <= result.context.timings.keys()

    path = calc.store(filename=tmp_path / "store-dftbp", format="json")
    assert path == tmp_path / "store-dftbp.json"
    [stored] = amac.load(path)
    assert stored.success is True
    assert stored.properties["forces"].shape == (6, 3)
    assert np.array_equal(stored.properties["positions"], image.get_positions())
    assert stored.properties["mass"] == pytest.approx(
        float(image.get_masses().sum()), rel=1e-12
    )
    provenance = stored.provenance
    assert (provenance["software"], provenance["driver"]) == ("DFTBP", "amac")
    assert provenance["spec"] == calc.spec.to_dict()
    assert provenance["exec_spec"]["cpu"] == 2
    assert provenance["duration"] > 0
    assert {"amac_version", "start", "end", "image"} <= provenance.keys()


def test_multiple_images_and_results_replaced(tmp_path, stub_calc):
    calc = stub_calc(workdir=tmp_path, label=None)
    calc.handler_properties(dftbplus.energy)
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


def test_raise_on_error_stops_at_failing_image(stub_calc):
    """The stub refuses one-atom images: the run stops there."""
    calc = stub_calc(stub={"fail_atoms": 1})
    calc.handler_properties(dftbplus.energy)
    with pytest.raises(RunError, match="code 3") as excinfo:
        calc.execute([water(), Atoms("H"), water()])
    assert len(excinfo.value.ctx.atoms) == 1
    assert [result.success for result in calc.results] == [True]


def test_failures_recorded_without_raise_on_error(stub_calc):
    """One image fails, one times out, the others succeed."""
    calc = stub_calc(
        stub={"fail_atoms": 1, "delay": 10, "delay_atoms": 2},
        raise_on_error=False,
        timeout=0.3,
    )
    calc.handler_properties(dftbplus.energy)
    images = [water(), Atoms("H"), Atoms("H2", positions=[[0, 0, 0], [0, 0, 0.74]])]
    results = calc.execute([*images, water()])

    assert [result.success for result in results] == [True, False, False, True]
    code_error, timeout_error = results[1].errors[0], results[2].errors[0]
    assert isinstance(code_error, RunError) and "code 3" in str(code_error)
    assert isinstance(timeout_error, RunError) and "timed out" in str(timeout_error)
    assert results[1].properties == results[2].properties == {}
    assert results[2].context.return_code is None
    assert results[3].properties["energy"] == pytest.approx(STUB_ENERGY * Hartree)


def test_overrides(stub_calc):
    calc = stub_calc(cpu=1)
    calc.handler_properties(dftbplus.energy)
    result = calc.execute(water(), cpu=4, label="override")
    assert result.context.exec_spec.cpu == 4
    assert result.provenance["exec_spec"]["label"] == "override"
    assert (calc.exec_spec.cpu, calc.exec_spec.label) == (1, "stub")
    with pytest.raises(TypeError, match="did you mean 'timeout'"):
        calc.execute(water(), timout=1)
    with pytest.raises(TypeError, match="'pbc'"):
        calc.execute(water(), pbc=False)
    with pytest.raises(ValueError, match="driver cannot be overridden"):
        calc.execute(water(), driver="auto")


def test_platform_alias(stub_calc, stub_spec, dftbp_configured):
    calculation = {key: value for key, value in stub_spec.items() if key != "software"}
    calc = AMAC(platform="DFTB+", **calculation)
    assert calc.software.name == "DFTBP"
    with pytest.raises(TypeError, match="exactly one"):
        AMAC(software="DFTB+", platform="DFTB+", **calculation)
    with pytest.raises(TypeError, match="exactly one"):
        AMAC(**calculation)


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"timout": 5}, "did you mean 'timeout'"),
        ({"method_arg": {}}, "did you mean 'method_args'"),
        ({"backend": "DFTB+"}, "Unknown argument 'backend'"),
        ({"run-delay": None}, "Unknown argument 'run-delay'"),
    ],
)
def test_unknown_arguments(stub_calc, kwargs, match):
    with pytest.raises(TypeError, match=match):
        stub_calc(**kwargs)


def test_validation_modes(stub_calc):
    """An invalid specification, in the three validation modes."""
    invalid = {
        "method_args": {"variant": "NOPE", "MaxAngularMomentum": {"O": "p", "H": "s"}}
    }
    with pytest.raises(ValidationError, match="NOPE"):
        stub_calc(validate="strict", **invalid)
    with pytest.warns(UserWarning, match="NOPE"):
        calc = stub_calc(validate="warn", **invalid)
    assert calc.issues and calc.validated
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert stub_calc(validate="off", **invalid).issues == []
    with pytest.raises(ValueError, match="validation mode"):
        stub_calc(validate="lenient")


def test_software_without_doc_cannot_be_validated(no_doc_calc):
    with pytest.raises(ValidationError, match="NO_DOC_TEST has no doc.json"):
        no_doc_calc(validate="strict")
    with pytest.warns(UserWarning, match="NO_DOC_TEST has no doc.json"):
        calc = no_doc_calc(validate="warn")
    assert (calc.issues, calc.validated) == ([], False)
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert no_doc_calc(validate="off").issues == []


@pytest.mark.parametrize("mode", ["warn", "off"])
@pytest.mark.filterwarnings("ignore:NO_DOC_TEST has no doc.json")
def test_provenance_says_a_run_was_not_validated(no_doc_calc, mode):
    calc = no_doc_calc(validate=mode)
    calc.handler_properties(("atom_count", lambda ctx: len(ctx.atoms)))
    assert calc.execute(water()).provenance["validated"] is False


def test_geometry_not_validated_without_doc(no_doc_calc):
    """Without ``doc.json``, a periodic geometry raises nothing."""
    periodic = Atoms("H", cell=[5.0, 5.0, 5.0], pbc=True)
    calc = no_doc_calc(validate="off")
    with warnings.catch_warnings():
        warnings.simplefilter("error", UserWarning)
        calc.handler_properties(("atom_count", lambda ctx: len(ctx.atoms)))
        assert calc.execute(periodic).success


def test_check_environment_fails_at_creation(stub_calc, monkeypatch):
    def incompatible(self):
        raise ConfigurationError("DFTBP: missing library")

    monkeypatch.setattr(DftbPlus, "check_environment", incompatible)
    # Validation would raise first if it came before the environment check.
    with pytest.raises(ConfigurationError, match="missing library"):
        stub_calc(
            validate="strict",
            method_args={"variant": "NOPE", "MaxAngularMomentum": {"O": "p"}},
        )


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
def test_invalid_geometry(stub_calc, geometry, error):
    with pytest.raises(error):
        stub_calc().execute(geometry)


def test_handler_properties_replaces_previous_handlers(stub_calc):
    calc = stub_calc()
    calc.handler_properties(dftbplus.energy)
    calc.handler_properties(dftbplus.forces)
    assert [meta.name for meta in calc.handlers] == ["forces"]
    with pytest.raises(ValueError, match="Duplicate result name"):
        calc.handler_properties(dftbplus.energy, ("energy", lambda ctx: 0.0))


def test_to_dict_from_dict(stub_calc):
    calc = stub_calc(cpu=2, label="calc", driver="auto")
    data = calc.to_dict()
    assert json.loads(json.dumps(data)) == data
    clone = AMAC.from_dict(data)
    assert clone.to_dict() == data
    assert "software='DFTBP'" in repr(clone)
    with pytest.raises(ValueError, match="AMAC data must have the keys"):
        AMAC.from_dict(data | {"unknown": []})


def test_store_formats(tmp_path, stub_calc):
    calc = stub_calc()
    path = calc.store(tmp_path / "empty.JSON")
    assert path == tmp_path / "empty.JSON"
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "format": "amac-results",
        "format_version": 1,
        "results": [],
    }
    with pytest.raises(NotImplementedError, match="yaml"):
        calc.store(tmp_path / "results", format="yaml")


# Serialization: secrets and handlers.


def test_to_dict_masks_secrets(stub_calc):
    calc = stub_calc(env={"TOKEN": "s3cr3t-value", "OMP_NUM_THREADS": "2"})
    masked = calc.to_dict()
    assert masked["exec_spec"]["env"] == {"TOKEN": "***", "OMP_NUM_THREADS": "***"}
    assert "s3cr3t-value" not in json.dumps(masked)
    clear = calc.to_dict(mask_secrets=False)
    assert clear["exec_spec"]["env"]["TOKEN"] == "s3cr3t-value"
    expected = "Masked environment variables are ignored: OMP_NUM_THREADS, TOKEN"
    with pytest.warns(UserWarning, match=expected):
        assert AMAC.from_dict(masked).exec_spec.env == {}
    assert AMAC.from_dict(clear).exec_spec.env == calc.exec_spec.env


def test_handlers_are_serialized(stub_calc):
    def local(ctx):
        return None

    calc = stub_calc()
    calc.handler_properties(
        dftbplus.energy,
        atom_count,
        ("size", output_size),
        ("anonymous", lambda ctx: 0),
        local,
    )
    with pytest.warns(UserWarning, match="Handlers not stored.*: anonymous, local"):
        data = calc.to_dict()
    assert data["handlers"] == [
        {"name": "energy", "handler": "amac.assets.dftbplus.handlers:energy"},
        {"name": "atom_count", "handler": f"{__name__}:atom_count"},
        {"name": "size", "handler": f"{__name__}:output_size"},
    ]
    clone = AMAC.from_dict(json.loads(json.dumps(data)))
    assert [meta.name for meta in clone.handlers] == ["energy", "atom_count", "size"]
    assert clone.handlers[2].requires_files == (DETAILED_OUT,)


def test_from_dict_skips_incompatible_handlers(stub_calc):
    data = stub_calc().to_dict()
    final = "amac.assets.dftbplus.handlers:final_geometry"
    data["handlers"] = [{"name": "final_geometry", "handler": final}]
    with pytest.warns(UserWarning, match="Incompatible handlers skipped"):
        assert AMAC.from_dict(data).handlers == []
    data["handlers"] = [{"name": "missing", "handler": "amac.assets.dftbplus:missing"}]
    with pytest.raises(ValueError, match="Cannot import the stored handler"):
        AMAC.from_dict(data)


# One specification per image.


def test_image_overrides(tmp_path, stub_calc):
    calc = stub_calc(workdir=tmp_path, label=None)
    calc.handler_properties(dftbplus.energy)
    overrides = {
        "method_args": {"SCCTolerance": 1e-8},
        "parameters": {"analysis": {"MullikenAnalysis": False}},
    }
    first, second = calc.execute([water(), (water(), overrides)])
    assert first.provenance["spec"] == calc.spec.to_dict()
    spec = second.provenance["spec"]
    assert spec["method_args"]["SCCTolerance"] == pytest.approx(1e-8)
    assert spec["method_args"]["variant"] == "DFTB2"
    assert spec["parameters"]["ANALYSIS"] == {
        "MullikenAnalysis": False,
        "Printforces": True,
    }
    assert second.context.spec.method_args["SCCTolerance"] == pytest.approx(1e-8)
    written = (second.context.directory / "dftb_in.hsd").read_text(encoding="utf-8")
    assert "SCCTolerance = 1e-08" in written or "SCCTolerance = 1.0e-08" in written
    assert "SCCTolerance" not in calc.spec.method_args

    single = calc.execute(
        (water(), {"method_args": {"SCCTolerance": 1e-4}}), label="pair"
    )
    assert isinstance(single, Result)
    assert single.context.directory == tmp_path / "pair"
    assert single.provenance["spec"]["method_args"]["SCCTolerance"] == pytest.approx(1e-4)


@pytest.mark.parametrize(
    ("overrides", "error", "match"),
    [
        ({"method": "DFT"}, ValueError, "cannot be overridden per image"),
        ({"module": "GEOMETRY_OPTIMISATION"}, ValueError, "cannot be overridden per image"),
        ({"cpu": 2}, ValueError, "Unknown image overrides"),
        ({"method_args": ["Charge"]}, TypeError, "must be a mapping"),
    ],
    ids=["method", "module", "unknown", "not-a-mapping"],
)
def test_invalid_image_overrides(stub_calc, overrides, error, match):
    with pytest.raises(error, match=match):
        stub_calc().execute([(water(), overrides)])


# Reprocessing.


def test_calc_reprocess(tmp_path, stub_calc):
    calc = stub_calc(workdir=tmp_path, label=None)
    calc.handler_properties(dftbplus.energy)
    result = calc.execute(water())
    provenance = result.provenance
    assert provenance["directory"] == str(tmp_path / "amac")
    assert (provenance["outdir"], provenance["reprocessed"]) == (None, False)

    again = calc.reprocess(
        result.context.directory, handlers=[dftbplus.charges, atom_count], atoms=water()
    )
    assert again.success
    assert again.properties["atom_count"] == 3
    assert again.properties["charges"] == pytest.approx(stub_charges(3))
    assert again.provenance["reprocessed"] is True
    assert [meta.name for meta in calc.handlers] == ["energy"]
    energy = calc.reprocess(result.context.directory).properties["energy"]
    assert energy == pytest.approx(STUB_ENERGY * Hartree)
    with pytest.raises(FileNotFoundError, match="does not exist"):
        calc.reprocess(tmp_path / "missing")


def test_reprocess_stored_result(tmp_path, stub_calc):
    calc = stub_calc(
        workdir=tmp_path / "work",
        outdir=tmp_path / "out",
        label="calc",
        env={"TOKEN": "secret"},
    )
    calc.handler_properties(dftbplus.energy)
    calc.execute(water())
    [stored] = amac.load(calc.store(tmp_path / "results"))
    assert stored.provenance["outdir"] == str(tmp_path / "out" / "calc")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        again = amac.reprocess(stored, [dftbplus.charges, atom_count])
    assert any("Masked environment" in str(item.message) for item in caught)
    assert again.properties["atom_count"] == 3
    assert again.context.directory == tmp_path / "work" / "calc"

    shutil.rmtree(tmp_path / "work")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        copy = amac.reprocess(stored, [dftbplus.energy])
        assert copy.context.directory == tmp_path / "out" / "calc"
        shutil.rmtree(tmp_path / "out")
        with pytest.raises(FileNotFoundError):
            amac.reprocess(stored, [dftbplus.energy])

    incomplete = Result(True, provenance={"software": "DFTBP", "spec": {}})
    with pytest.raises(ValueError, match="lacks exec_spec, directory"):
        amac.reprocess(incomplete, [dftbplus.energy])


# Where the files are written.


def test_workdir_is_absolute_and_in_the_repr(stub_calc, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    calc = stub_calc(workdir="runs")
    assert calc.workdir == (tmp_path / "runs").resolve()
    assert calc.exec_spec.workdir == Path("runs")  # the spec keeps what was given
    assert f"workdir='{calc.workdir}'" in repr(calc)


def test_workdir_expands_the_home_directory(stub_calc, tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    assert stub_calc(workdir="~/amac-runs").workdir == tmp_path / "amac-runs"


def test_directories_of_the_last_execute(stub_calc, tmp_path):
    calc = stub_calc(workdir=tmp_path, label="runs")
    assert calc.directories == []
    calc.handler_properties(dftbplus.energy)

    calc.execute(water())
    assert calc.directories == [tmp_path / "runs"]
    results = calc.execute([water(), water()])
    assert calc.directories == [
        tmp_path / "runs" / "image_000",
        tmp_path / "runs" / "image_001",
    ]
    assert calc.directories == [result.context.directory for result in results]
    # The same paths are in the provenance, so a stored result keeps them.
    assert [result.provenance["directory"] for result in results] == [
        str(path) for path in calc.directories
    ]


def test_a_workdir_override_does_not_change_the_calculator(stub_calc, tmp_path):
    calc = stub_calc(workdir=tmp_path / "default", label="runs")
    calc.handler_properties(dftbplus.energy)
    result = calc.execute(water(), workdir=tmp_path / "other")

    assert result.context.directory == tmp_path / "other" / "runs"
    assert calc.workdir == (tmp_path / "default").resolve()
    assert calc.directories == [tmp_path / "other" / "runs"]


def test_each_run_logs_its_directory(stub_calc, tmp_path, caplog):
    calc = stub_calc(workdir=tmp_path, label="runs")
    calc.handler_properties(dftbplus.energy)
    with caplog.at_level(logging.INFO, logger="amac.amac"):
        calc.execute([water(), water()])

    messages = [record.getMessage() for record in caplog.records]
    assert messages == [
        f"DFTBP: run directory {tmp_path / 'runs' / 'image_000'} (image 0)",
        f"DFTBP: run directory {tmp_path / 'runs' / 'image_001'} (image 1)",
    ]


def test_a_single_image_logs_without_an_image_number(stub_calc, tmp_path, caplog):
    calc = stub_calc(workdir=tmp_path, label="runs")
    calc.handler_properties(dftbplus.energy)
    with caplog.at_level(logging.INFO, logger="amac.amac"):
        calc.execute(water())
    assert caplog.records[0].getMessage() == f"DFTBP: run directory {tmp_path / 'runs'}"


def test_amac_installs_no_logging_handler():
    """A library writes nothing on its own: only a NullHandler is installed."""
    handlers = logging.getLogger("amac").handlers
    assert [type(handler) for handler in handlers] == [logging.NullHandler]
