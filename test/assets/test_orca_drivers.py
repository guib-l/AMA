"""Tests of the ORCA cclib driver, without cclib and without ORCA."""

from types import SimpleNamespace

import numpy as np
import pytest
from ase.units import Hartree, invcm

from amac.assets.orca.drivers import OrcaCclibDriver
from amac.assets.orca.orca import Orca
from amac.assets.orca.parser import OrcaOutput
from amac.exceptions import DriverUnavailableError
from amac.engine.drivers import select_driver


def cc_data(**overrides) -> SimpleNamespace:
    """Return a minimal ``ccData`` as cclib fills it, in cclib units."""
    values = {
        "scfenergies": np.asarray([-2068.8, -2069.1]),  # eV
        "grads": np.asarray([[[1e-4, 2e-4, 3e-4], [-1e-4, -2e-4, -3e-4]]]),
        "atomcharges": {"mulliken": np.asarray([-0.4, 0.4])},
        "moenergies": [np.asarray([-516.9, -27.1])],  # eV
        "vibfreqs": np.asarray([1638.62]),
        "etenergies": np.asarray([62862.5]),  # cm^-1
        "atomcoords": np.asarray([[[0.0, 0.0, 0.0], [0.0, 0.0, 0.74]]]),
        "atomnos": np.asarray([1, 1]),
        "metadata": {"success": True},
    }
    return SimpleNamespace(**values | overrides)


def test_driver_attributes():
    driver = OrcaCclibDriver()
    assert (driver.NAME, driver.REQUIRES, driver.DISTRIBUTION) == (
        "cclib",
        ("cclib",),
        "cclib",
    )
    assert driver.PHASES == frozenset({"collect"})
    assert driver.OUTPUT_FILE == "orca.out"
    assert Orca.DRIVERS == (OrcaCclibDriver,)


def test_cclib_is_the_only_driver_and_is_refused_when_missing():
    with pytest.raises(DriverUnavailableError, match="pip install cclib"):
        select_driver(Orca, "cclib")


def test_auto_falls_back_to_the_amac_path_without_cclib():
    selection = select_driver(Orca, "auto")
    assert selection.name == "amac"
    assert "cclib" in selection.fallback


def test_to_output_converts_to_the_units_of_the_program():
    output = OrcaCclibDriver().to_output(cc_data())

    assert isinstance(output, OrcaOutput)
    assert output.energy == pytest.approx(-2069.1 / Hartree)
    assert output.orbital_energies == pytest.approx(np.asarray([-516.9, -27.1]) / Hartree)
    assert output.excitations == pytest.approx(62862.5 * invcm / Hartree)
    # The gradient of cclib is already in Hartree/Bohr; forces are its opposite.
    assert output.forces[0] == pytest.approx([-1e-4, -2e-4, -3e-4])
    assert output.frequencies == pytest.approx([1638.62])
    assert output.charges["mulliken"] == pytest.approx([-0.4, 0.4])
    assert output.final_geometry.get_chemical_symbols() == ["H", "H"]
    assert output.terminated_normally is True
    assert output.files == ("orca.out",)


def test_to_output_of_a_bare_calculation():
    output = OrcaCclibDriver().to_output(SimpleNamespace())

    assert output.energy is None
    assert output.forces is None
    assert output.charges == {}
    assert output.final_geometry is None
    assert output.terminated_normally is False
