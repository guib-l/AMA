"""Tests of amac.engine.backend, the legacy attribute proxy (not used by AMAC)."""

import pytest

from amac.engine.backend import Backend, mandatory_backend


class Alpha:
    def __init__(self, value=None):
        self.value = value

    def a(self):
        return 5.0

    def b(self):
        return 15.0


class Beta:
    def __init__(self, data=None):
        self.data = data

    def a(self, **kwargs):
        return 3.0

    def c(self):
        return 9.0


def make_atoms_class() -> type[Backend]:
    """Return a new Backend subclass: its pool of backends is class-level state."""
    binding = {
        "object_A": {
            "object": Alpha,
            "attributes": ["value"],
            "binding": {"value": "data"},
        },
        "object_B": {
            "object": Beta,
            "attributes": ["data"],
            "binding": {"b": "d"},
        },
    }

    class Atoms(Backend, binding=binding):
        def __init__(self, data=None, **backend):
            super().__init__(**backend)
            self.data = data

        def a(self, value=1.0):
            return 1.0 * value

        def d(self):
            return 4.0

        @mandatory_backend(["object_B"])
        def restricted(self):
            return f"backend: {self._active_backend}"

    return Atoms


@pytest.fixture
def atoms():
    return make_atoms_class()(data={"dat": 1}, backend="object_A")


def test_local_method_wins(atoms):
    assert atoms.a(value=2.0) == pytest.approx(2.0, abs=1e-12)
    assert atoms.data == {"dat": 1}


def test_missing_attribute_is_read_on_active_backend(atoms):
    assert atoms._active_backend == "object_A"
    assert atoms.b() == pytest.approx(15.0, abs=1e-12)


def test_switch_backend_and_binding(atoms):
    atoms.switch_backend("object_B")
    assert atoms._active_backend == "object_B"
    assert atoms.c() == pytest.approx(9.0, abs=1e-12)
    # "b" is bound to "d", absent from Beta and found on the class itself.
    assert atoms.b() == pytest.approx(4.0, abs=1e-12)


def test_switch_to_unknown_backend(atoms):
    with pytest.raises(ValueError, match='Backend "object_C" not found'):
        atoms.switch_backend("object_C")


def test_mandatory_backend(atoms):
    with pytest.raises(RuntimeError, match="requires one of these backends"):
        atoms.restricted()
    atoms.switch_backend("object_B")
    assert atoms.restricted() == "backend: object_B"


def test_empty_backend_name():
    with pytest.raises(RuntimeError, match="No active backend"):
        make_atoms_class()(backend="")


def test_required_methods_are_enforced():
    with pytest.raises(TypeError, match="needs to define method run"):

        class Incomplete(Backend, binding={}):
            REQUIRED_METHODS = ("run",)


@pytest.mark.xfail(
    raises=RecursionError,
    strict=True,
    reason="BaseCheck.__getattr__ calls hasattr(self, name), which recurses "
    "instead of raising AttributeError",
)
def test_unknown_attribute_raises_attribute_error(atoms):
    with pytest.raises(AttributeError):
        _ = atoms.missing


@pytest.mark.xfail(
    raises=RuntimeError,
    strict=True,
    reason="Backend.__init__ replaces the classes of the class-level pool by "
    "instances, so a second instance of the same class cannot be created",
)
def test_two_instances_of_the_same_class():
    atoms_class = make_atoms_class()
    atoms_class(backend="object_A")
    assert atoms_class(backend="object_B")._active_backend == "object_B"
