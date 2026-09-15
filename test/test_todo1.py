"""Tests of the TODO-1 corrections (points 1, 2 and 4 to 10; point 3 elsewhere).

Point 3 is tested in ``test_doc_features.py``.
"""

import importlib
import json
import shutil
import warnings

import pytest
from ase import Atoms

import amac
from amac import AMAC, exceptions
from amac.assets import _dummy
from amac.assets._dummy.dummy import DummySoftware
from amac.engine import registry
from amac.engine.context import Result
from amac.engine.handlers import HANDLER_ATTRIBUTE, handler

PARAMETERS = {
    "method": "DFT",
    "method_args": {"variant": "PBE"},
    "parameters": {"BASIS": "sto-3g"},
}


def water() -> Atoms:
    positions = [[0.0, 0.0, 0.0], [0.76, 0.59, 0.0], [-0.76, 0.59, 0.0]]
    return Atoms("OH2", positions=positions)


def make_calc(tmp_path, **kwargs) -> AMAC:
    return AMAC(**{"software": "dummy", "workdir": tmp_path, **PARAMETERS} | kwargs)


def atom_count(ctx) -> int:
    """Module-level custom handler, importable as ``<module>:atom_count``."""
    return len(ctx.atoms)


@handler(requires_files=("output.json",))
def output_size(ctx) -> int:
    """Custom handler with requires_files, attached to no software."""
    return ctx.files["output.json"].stat().st_size


@handler(modules=("GEOMETRY_OPTIMISATION",))
def final_step(ctx) -> None:
    """Custom handler restricted to optimisations."""


@pytest.fixture
def isolated_registry(monkeypatch):
    monkeypatch.setattr(registry, "_REGISTRY", dict(registry._REGISTRY))
    return registry.register_software


@pytest.fixture
def facade_state(monkeypatch):
    monkeypatch.setattr(amac, "_STATE", amac._FacadeState())


# 1. Software without doc.json


def test_software_without_doc(tmp_path, isolated_registry):
    class DoclessSoftware(DummySoftware):
        NAME = "DOCLESS_TEST"
        DOC = None

    isolated_registry(DoclessSoftware)
    with pytest.raises(amac.ValidationError, match="DOCLESS_TEST has no doc.json"):
        make_calc(tmp_path, software="docless_test")
    with pytest.warns(UserWarning, match="validate='off'"):
        lenient = make_calc(tmp_path, software="docless_test", validate="warn")
    assert not lenient.validated
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        silent = make_calc(tmp_path, software="docless_test", validate="off")
    assert not silent.validated


@pytest.mark.parametrize(("mode", "expected"), [("strict", True), ("off", False)])
def test_provenance_validated(tmp_path, mode, expected):
    calc = make_calc(tmp_path, validate=mode)
    calc.handler_properties(_dummy.energy)
    assert calc.execute(water()).provenance["validated"] is expected


# 2. Lowercase software packages


def test_software_packages_are_lowercase():
    for name in ("orca", "gaussian", "dftbplus", "demonnano"):
        package = importlib.import_module(f"amac.assets.{name}")
        assert f"from amac.assets import {name}" in package.__doc__
    assert registry.get_software("DFTB+").DOC.parent.name == "dftbplus"


# 4. validate through configure


def test_configure_validate(tmp_path, facade_state):
    amac.configure(validate="warn")
    assert amac.calculator(PARAMETERS, "dummy", workdir=tmp_path).validate == "warn"
    amac.configure(software="dummy", validate="off")
    assert amac.calculator(PARAMETERS, "dummy").validate == "off"
    assert amac.calculator(PARAMETERS, "dummy", validate="strict").validate == "strict"
    assert AMAC(software="dummy", **PARAMETERS).validate == "strict"
    with pytest.raises(ValueError, match="Unknown validation mode 'lenient'"):
        amac.configure(validate="lenient")


# 5. to_dict: secrets and handlers


def test_to_dict_masks_secrets(tmp_path):
    calc = make_calc(tmp_path, env={"TOKEN": "s3cr3t-value", "OMP_NUM_THREADS": "2"})
    masked = calc.to_dict()
    assert masked["exec_spec"]["env"] == {"TOKEN": "***", "OMP_NUM_THREADS": "***"}
    assert "s3cr3t-value" not in json.dumps(masked)
    clear = calc.to_dict(mask_secrets=False)
    assert clear["exec_spec"]["env"]["TOKEN"] == "s3cr3t-value"
    expected = "Masked environment variables are ignored: OMP_NUM_THREADS, TOKEN"
    with pytest.warns(UserWarning, match=expected):
        assert AMAC.from_dict(masked).exec_spec.env == {}
    assert AMAC.from_dict(clear).exec_spec.env == calc.exec_spec.env


def test_handlers_are_serialized(tmp_path):
    def local(ctx):
        return None

    calc = make_calc(tmp_path)
    calc.handler_properties(
        _dummy.energy,
        atom_count,
        ("size", output_size),
        ("anonymous", lambda ctx: 0),
        local,
    )
    with pytest.warns(UserWarning, match="Handlers not stored.*: anonymous, local"):
        data = calc.to_dict()
    assert data["handlers"] == [
        {"name": "energy", "handler": "amac.assets._dummy.handlers:energy"},
        {"name": "atom_count", "handler": f"{__name__}:atom_count"},
        {"name": "size", "handler": f"{__name__}:output_size"},
    ]
    clone = AMAC.from_dict(json.loads(json.dumps(data)))
    assert [meta.name for meta in clone.handlers] == ["energy", "atom_count", "size"]
    assert clone.handlers[2].requires_files == ("output.json",)


def test_from_dict_skips_incompatible_handlers(tmp_path):
    data = make_calc(tmp_path).to_dict()
    native = "amac.assets._dummy.handlers:native_energy"
    data["handlers"] = [{"name": "native_energy", "handler": native}]
    with pytest.warns(UserWarning, match="Incompatible handlers skipped"):
        assert AMAC.from_dict(data).handlers == []
    data["handlers"] = [{"name": "missing", "handler": "amac.assets._dummy:missing"}]
    with pytest.raises(ValueError, match="Cannot import the stored handler"):
        AMAC.from_dict(data)


# 6. Spec per image


def test_image_overrides(tmp_path):
    scf = {"MaxIter": 50, "Tolerance": 1e-6}
    calc = make_calc(tmp_path, parameters={"BASIS": "sto-3g", "SCF": scf})
    calc.handler_properties(_dummy.energy)
    overrides = {"method_args": {"Charge": 1}, "parameters": {"scf": {"MaxIter": 80}}}
    first, second = calc.execute([water(), (water(), overrides)])
    assert first.provenance["spec"] == calc.spec.to_dict()
    spec = second.provenance["spec"]
    assert spec["method_args"] == {"variant": "PBE", "Charge": 1}
    assert spec["parameters"]["SCF"] == {"MaxIter": 80, "Tolerance": 1e-6}
    assert second.context.spec.method_args["Charge"] == 1
    tree = json.loads((second.context.directory / "input.json").read_text("utf-8"))
    dft = tree["nodes"]["Hamiltonian"]["children"]["DFT"]["children"]
    assert dft["Charge"]["value"] == 1
    assert calc.spec.method_args == {"variant": "PBE"}

    single = calc.execute((water(), {"parameters": {"BASIS": "6-31g"}}), label="pair")
    assert isinstance(single, Result)
    assert single.context.directory == tmp_path / "pair"
    assert single.provenance["spec"]["parameters"]["BASIS"] == "6-31g"


@pytest.mark.parametrize(
    ("overrides", "error", "match"),
    [
        ({"method": "HF"}, ValueError, "cannot be overridden per image"),
        ({"module": "OPT"}, ValueError, "cannot be overridden per image"),
        ({"cpu": 2}, ValueError, "Unknown image overrides"),
        ({"method_args": ["Charge"]}, TypeError, "must be a mapping"),
    ],
    ids=["method", "module", "unknown", "not-a-mapping"],
)
def test_invalid_image_overrides(tmp_path, overrides, error, match):
    with pytest.raises(error, match=match):
        make_calc(tmp_path).execute([(water(), overrides)])


def test_image_overrides_are_validated(tmp_path):
    calc = make_calc(tmp_path)
    calc.handler_properties(_dummy.energy)
    with pytest.raises(amac.ValidationError, match="Multiplicity"):
        calc.execute([(water(), {"method_args": {"Multiplicity": 99}})])
    assert calc.results == []
    assert not (tmp_path / "amac").exists()
    lenient = make_calc(tmp_path, validate="warn", label="lenient")
    lenient.handler_properties(_dummy.energy)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        [result] = lenient.execute([(water(), {"method_args": {"Multiplicity": 99}})])
    assert any("Multiplicity" in str(item.message) for item in caught)
    assert result.success


# 7. Handler without software


def test_handler_without_software(tmp_path):
    assert getattr(output_size, HANDLER_ATTRIBUTE).software is None
    assert "output_size" not in DummySoftware.HANDLERS
    calc = make_calc(tmp_path)
    calc.handler_properties(output_size)
    assert calc.execute(water()).properties["output_size"] > 0
    in_process = make_calc(tmp_path, software="dummy-inprocess", label="in-process")
    in_process.handler_properties(output_size)
    [error] = in_process.execute(water()).errors
    assert error.missing_files == ("output.json",)


# 8. skip_incompatible


def test_skip_incompatible(tmp_path):
    auto = make_calc(tmp_path, driver="auto")
    with pytest.warns(UserWarning, match="native_energy.*fell back to it: dummy-lib"):
        auto.handler_properties(
            _dummy.energy, _dummy.native_energy, final_step, skip_incompatible=True
        )
    assert [meta.name for meta in auto.handlers] == ["energy"]
    with pytest.raises(ValueError, match="Duplicate result name"):
        auto.handler_properties(
            _dummy.energy, ("energy", atom_count), skip_incompatible=True
        )
    with pytest.raises(ValueError, match="module 'SINGLE_POINT'"):
        auto.handler_properties(final_step)


def test_skip_incompatible_in_facade(tmp_path, facade_state):
    handlers = [_dummy.energy, _dummy.native_energy]
    with pytest.warns(UserWarning, match="native_energy"):
        calc = amac.calculator(
            PARAMETERS,
            "dummy",
            handlers=handlers,
            skip_incompatible=True,
            workdir=tmp_path,
        )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = amac.run(
            water(),
            handlers=[_dummy.native_energy, _dummy.forces],
            skip_incompatible=True,
        )
    assert any("native_energy" in str(item.message) for item in caught)
    assert result.properties.keys() == {"forces"}
    assert [meta.name for meta in calc.handlers] == ["energy"]


# 9. Reprocessing


def test_calc_reprocess(tmp_path):
    calc = make_calc(tmp_path)
    calc.handler_properties(_dummy.energy)
    result = calc.execute(water())
    provenance = result.provenance
    assert provenance["directory"] == str(tmp_path / "amac")
    assert (provenance["outdir"], provenance["reprocessed"]) == (None, False)

    again = calc.reprocess(
        result.context.directory, handlers=[_dummy.forces, atom_count], atoms=water()
    )
    assert again.success
    assert again.properties == {"forces": [], "atom_count": 3}
    assert again.provenance["reprocessed"] is True
    assert [meta.name for meta in calc.handlers] == ["energy"]
    energy = calc.reprocess(result.context.directory).properties["energy"]
    assert energy == pytest.approx(-1.0, abs=1e-12)
    with pytest.raises(FileNotFoundError, match="does not exist"):
        calc.reprocess(tmp_path / "missing")


def test_reprocess_stored_result(tmp_path):
    calc = make_calc(
        tmp_path,
        workdir=tmp_path / "work",
        outdir=tmp_path / "out",
        label="calc",
        env={"TOKEN": "secret"},
    )
    calc.handler_properties(_dummy.energy)
    calc.execute(water())
    [stored] = amac.load(calc.store(tmp_path / "results"))
    assert stored.provenance["outdir"] == str(tmp_path / "out" / "calc")

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        again = amac.reprocess(stored, [_dummy.forces, atom_count])
    assert any("Masked environment" in str(item.message) for item in caught)
    assert again.properties == {"forces": [], "atom_count": 3}
    assert again.context.directory == tmp_path / "work" / "calc"

    shutil.rmtree(tmp_path / "work")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        copy = amac.reprocess(stored, [_dummy.forces])
        assert copy.context.directory == tmp_path / "out" / "calc"
        shutil.rmtree(tmp_path / "out")
        with pytest.raises(FileNotFoundError):
            amac.reprocess(stored, [_dummy.forces])

    incomplete = Result(True, provenance={"software": "DUMMY", "spec": {}})
    with pytest.raises(ValueError, match="lacks exec_spec, directory"):
        amac.reprocess(incomplete, [_dummy.forces])


# 10. Exported exceptions


def test_exceptions_are_exported(tmp_path):
    names = (
        "AMACError",
        "ValidationError",
        "SoftwareNotFoundError",
        "RunError",
        "HandlerError",
        "DriverUnavailableError",
    )
    for name in names:
        assert getattr(amac, name) is getattr(exceptions, name)
        assert name in amac.__all__
    with pytest.raises(amac.ValidationError):
        make_calc(tmp_path, method_args={"variant": "PBE0"})
