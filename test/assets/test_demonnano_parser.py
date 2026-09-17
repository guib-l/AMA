"""Tests of the deMonNano parser, on synthetic excerpts and without the library."""

import numpy as np
import pytest
from ase import Atoms

from amac.assets.demonnano.parser import (
    DemonNanoOutput,
    from_results,
    parse_dipole,
    parse_directory,
    parse_energies,
    parse_errors,
    parse_forces_file,
    parse_geometries,
    parse_gradient,
    parse_orbital_energies,
)

OUT = """\
 deMonNano, DFTB calculation

 DFTB Eigen values
 Occupied Eigen values   -0.8500  -0.4300
 Virtual Eigen values     0.1200
 DFTB band energy                     :       -2.5600000000
 DFTB repulsive energy                :        0.0500000000
 DFTB total energy                    :       -4.0710651894

                    CARTESIAN GRADIENT
    1 O      0.00100000     0.00200000    -0.00300000
    2 H     -0.00050000     0.00000000     0.00150000
    3 H     -0.00050000    -0.00200000     0.00150000

 mass center      =   0.000000   0.065000   0.000000
 charge dipole    =   0.000000   0.730000   0.000000
 norme dipole     =   0.730000
"""

MOL = """\
3
 step 1 -4.0500000000
O    0.0000000    0.0000000    0.0000000   -0.6000000
H    0.7570000    0.5860000    0.0000000    0.3000000
H   -0.7570000    0.5860000    0.0000000    0.3000000
3
 step 2 -4.0710651894
O    0.0000000    0.0100000    0.0000000   -0.6200000
H    0.7600000    0.5900000    0.0000000    0.3100000
H   -0.7600000    0.5900000    0.0000000    0.3100000
"""

FORCES = """\
 forces
   0.0010000   0.0020000  -0.0030000
  -0.0005000   0.0000000   0.0015000
  -0.0005000  -0.0020000   0.0015000
"""


def test_parse_energies():
    energies = parse_energies(OUT)
    assert energies["energy"] == pytest.approx(-4.0710651894)
    assert energies["band_energy"] == pytest.approx(-2.56)
    assert energies["repulsive_energy"] == pytest.approx(0.05)
    assert "coulomb_energy" not in energies


def test_parse_energies_keeps_the_last_value():
    text = OUT + " DFTB total energy                    :       -4.1000000000\n"
    assert parse_energies(text)["energy"] == pytest.approx(-4.1)


def test_parse_gradient():
    gradient = parse_gradient(OUT)
    assert gradient.shape == (3, 3)
    assert gradient[0] == pytest.approx([0.001, 0.002, -0.003])
    assert parse_gradient("no block here") is None


def test_parse_dipole():
    assert parse_dipole(OUT) == pytest.approx([0.0, 0.73, 0.0])
    assert parse_dipole("nothing") is None


def test_parse_orbital_energies():
    assert parse_orbital_energies(OUT) == pytest.approx([-0.85, -0.43, 0.12])
    assert parse_orbital_energies("nothing") is None


def test_parse_errors():
    assert parse_errors(OUT) == ((), True)
    messages, converged = parse_errors(" ERROR : something went wrong\n")
    assert (messages, converged) == (("something went wrong",), None)
    messages, converged = parse_errors(OUT + " optimization not converged\n")
    assert converged is False and "optimization not converged" in messages


def test_parse_geometries():
    images = parse_geometries(MOL)
    assert [len(image) for image in images] == [3, 3]
    assert images[-1].get_positions()[0] == pytest.approx([0.0, 0.01, 0.0])
    assert images[-1].get_initial_charges() == pytest.approx([-0.62, 0.31, 0.31])
    assert list(images[0].symbols) == ["O", "H", "H"]


def test_parse_geometries_drops_dummy_atoms():
    text = "2\n comment\nO 0.0 0.0 0.0\nXx 1.0 0.0 0.0\n"
    (image,) = parse_geometries(text)
    assert list(image.symbols) == ["O"]


def test_parse_forces_file():
    forces = parse_forces_file(FORCES)
    assert forces.shape == (3, 3)
    assert forces[0] == pytest.approx([0.001, 0.002, -0.003])


def test_parse_directory(tmp_path):
    (tmp_path / "deMon.out").write_text(OUT, encoding="utf-8")
    (tmp_path / "deMon.mol").write_text(MOL, encoding="utf-8")
    output = parse_directory(tmp_path)
    assert output.energy == pytest.approx(-4.0710651894)
    # Forces are the opposite of the gradient, still in Hartree/Bohr.
    assert output.forces[0] == pytest.approx([-0.001, -0.002, 0.003])
    assert output.charges == pytest.approx([-0.62, 0.31, 0.31])
    assert output.dipole == pytest.approx([0.0, 0.73, 0.0])
    assert len(output.trajectory) == 2
    assert output.final_geometry.get_positions()[0] == pytest.approx([0.0, 0.01, 0.0])
    assert output.converged is True
    assert output.files == ("deMon.out", "deMon.mol")


def test_parse_directory_prefers_the_forces_file(tmp_path):
    (tmp_path / "deMon.out").write_text(OUT, encoding="utf-8")
    (tmp_path / "forces.out").write_text(FORCES, encoding="utf-8")
    output = parse_directory(tmp_path)
    assert output.forces[0] == pytest.approx([0.001, 0.002, -0.003])


def test_parse_directory_of_an_empty_run(tmp_path):
    assert parse_directory(tmp_path) == DemonNanoOutput()


def test_from_results():
    geometry = Atoms("H2", positions=[[0.0, 0.0, 0.0], [0.0, 0.0, 0.74]])
    geometry.set_initial_charges([-0.1, 0.1])
    output = from_results(
        {
            "energy": {"energy": -1.2, "band_energy": -0.9},
            "output_geometry": geometry,
            "trajectory": [geometry, geometry],
            "moe": {"occupied": [-0.5], "virtual": [0.3]},
            "converged": False,
            "errors": [{"kind": "optimization", "message": "not converged"}],
        }
    )
    assert output.energy == pytest.approx(-1.2)
    assert output.energies["band_energy"] == pytest.approx(-0.9)
    assert output.charges == pytest.approx([-0.1, 0.1])
    assert output.orbital_energies == pytest.approx([-0.5, 0.3])
    assert output.final_geometry is geometry
    assert len(output.trajectory) == 2
    assert output.converged is False
    assert output.errors == ("[optimization] not converged",)


def test_from_results_of_an_empty_run():
    output = from_results({})
    assert (output.energy, output.charges, output.final_geometry) == (None, None, None)
    assert np.asarray(output.trajectory).size == 0
