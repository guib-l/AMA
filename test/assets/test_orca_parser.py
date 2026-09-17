"""Tests of the ORCA parser, on synthetic extracts and on real outputs if present.

The extracts below are the shapes the parser looks for, not whole ORCA files. The
tests reading ``test/fixtures/orca/`` are skipped until real outputs are placed
there; they then run without any change.
"""

from pathlib import Path

import numpy as np
import pytest

from amac.assets.orca.parser import (
    OrcaOutput,
    parse_directory,
    parse_engrad,
    parse_hessian,
    parse_output,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "orca"
needs_fixtures = pytest.mark.skipif(
    not (FIXTURES / "orca.out").is_file(),
    reason="no real ORCA output in test/fixtures/orca/",
)

OUTPUT = """\
                         ORCA SCF
----------------------------
FINAL SINGLE POINT ENERGY       -76.026760737234

-----------------------
MULLIKEN ATOMIC CHARGES
-----------------------
   0 O :   -0.377875
   1 H :    0.188937
   2 H :    0.188938
Sum of atomic charges:   -0.0000000

----------------------
LOEWDIN ATOMIC CHARGES
----------------------
   0 O :   -0.240000
   1 H :    0.120000
   2 H :    0.120000

----------------
ORBITAL ENERGIES
----------------
  NO   OCC          E(Eh)            E(eV)
   0   2.0000     -18.995659      -516.9047
   1   2.0000      -0.995659       -27.0932
   2   0.0000       0.155659         4.2357

-------------
DIPOLE MOMENT
-------------
Total Dipole Moment    :     -0.000000000      -0.000000000       0.330260168

-----------------------
VIBRATIONAL FREQUENCIES
-----------------------

Scaling factor for frequencies =  1.000000000

   0:         0.00 cm**-1
   5:      1638.62 cm**-1
   6:      3812.50 cm**-1

STATE  1:  E=   0.286451 au      7.794 eV   62862.5 cm**-1
STATE  2:  E=   0.350000 au      9.524 eV   76821.0 cm**-1

                             ****ORCA TERMINATED NORMALLY****
"""

ENGRAD = """\
#
# Number of atoms
#
 3
#
# The current total energy in Eh
#
    -76.026760737234
#
# The current gradient in Eh/bohr
#
     0.000100000000
     0.000200000000
     0.000300000000
    -0.000100000000
    -0.000200000000
    -0.000300000000
     0.000000000000
     0.000000000000
     0.000000000000
#
# The atomic numbers and current coordinates in Bohr
#
    8     0.0000000    0.0000000    0.2216932
    1     0.0000000    1.4308000   -0.8867726
    1     0.0000000   -1.4308000   -0.8867726
"""

HESS = """\
$orca_hessian_file

$act_atom
  0

$hessian
4
                  0          1          2          3
      0       1.000000   0.100000   0.000000   0.000000
      1       0.100000   2.000000   0.000000   0.000000
      2       0.000000   0.000000   3.000000   0.200000
      3       0.000000   0.000000   0.200000   4.000000

$vibrational_frequencies
4
    0       0.000000
    1       0.000000
    2    1638.620000
    3    3812.500000

$end
"""


def test_parse_output_reads_the_energy_and_the_termination():
    values = parse_output(OUTPUT)
    assert values["energy"] == pytest.approx(-76.026760737234)
    assert values["terminated_normally"] is True


def test_parse_output_reads_both_population_analyses():
    charges = parse_output(OUTPUT)["charges"]
    assert set(charges) == {"mulliken", "loewdin"}
    assert charges["mulliken"] == pytest.approx([-0.377875, 0.188937, 0.188938])
    assert charges["loewdin"] == pytest.approx([-0.24, 0.12, 0.12])


def test_parse_output_reads_the_dipole_in_atomic_units():
    assert parse_output(OUTPUT)["dipole"] == pytest.approx([0.0, 0.0, 0.330260168])


def test_parse_output_reads_the_orbital_energies_in_hartree():
    values = parse_output(OUTPUT)
    assert values["orbital_energies"] == pytest.approx([-18.995659, -0.995659, 0.155659])
    assert values["occupations"] == pytest.approx([2.0, 2.0, 0.0])


def test_parse_output_reads_the_frequencies_and_the_excitations():
    values = parse_output(OUTPUT)
    assert values["frequencies"] == pytest.approx([0.0, 1638.62, 3812.5])
    assert values["excitations"] == pytest.approx([0.286451, 0.35])


def test_parse_output_of_an_empty_run():
    values = parse_output("nothing useful here\n")
    assert values == {"terminated_normally": False}


def test_parse_engrad_returns_forces_opposite_to_the_gradient():
    values = parse_engrad(ENGRAD)
    assert values["energy"] == pytest.approx(-76.026760737234)
    assert values["forces"].shape == (3, 3)
    assert values["forces"][0] == pytest.approx([-1e-4, -2e-4, -3e-4])


def test_parse_engrad_of_a_truncated_file():
    with pytest.raises(ValueError, match="expected 9 gradient values"):
        parse_engrad("3\n-76.0\n0.1 0.2\n")


def test_parse_hessian_reads_the_matrix_and_the_frequencies():
    values = parse_hessian(HESS)
    matrix = values["hessian"]
    assert matrix.shape == (4, 4)
    assert matrix[0, 1] == pytest.approx(0.1)
    assert matrix[3, 3] == pytest.approx(4.0)
    assert np.allclose(matrix, matrix.T)
    assert values["frequencies"] == pytest.approx([0.0, 0.0, 1638.62, 3812.5])


def test_parse_directory_gathers_every_file(tmp_path):
    (tmp_path / "orca.out").write_text(OUTPUT, encoding="utf-8")
    (tmp_path / "orca.engrad").write_text(ENGRAD, encoding="utf-8")
    (tmp_path / "orca.hess").write_text(HESS, encoding="utf-8")

    output = parse_directory(tmp_path)
    assert isinstance(output, OrcaOutput)
    assert output.files == ("orca.out", "orca.engrad", "orca.hess")
    assert output.energy == pytest.approx(-76.026760737234)
    assert output.forces.shape == (3, 3)
    assert output.hessian.shape == (4, 4)
    # The log gives the frequencies; the Hessian file does not overwrite them.
    assert output.frequencies == pytest.approx([0.0, 1638.62, 3812.5])


def test_parse_directory_of_an_empty_directory(tmp_path):
    output = parse_directory(tmp_path)
    assert output == OrcaOutput()


def test_parse_directory_reads_the_final_geometry(tmp_path):
    (tmp_path / "orca.out").write_text(OUTPUT, encoding="utf-8")
    (tmp_path / "orca.xyz").write_text(
        "2\nH2\nH 0.0 0.0 0.0\nH 0.0 0.0 0.74\n", encoding="utf-8"
    )
    output = parse_directory(tmp_path)
    assert output.final_geometry.get_chemical_symbols() == ["H", "H"]


@needs_fixtures
def test_real_output_is_parsed():
    output = parse_directory(FIXTURES)
    assert output.energy is not None
    assert output.terminated_normally


@needs_fixtures
@pytest.mark.skipif(
    not (FIXTURES / "orca.engrad").is_file(), reason="no orca.engrad fixture"
)
def test_real_engrad_is_parsed():
    values = parse_engrad((FIXTURES / "orca.engrad").read_text(encoding="utf-8"))
    assert values["forces"].shape[1] == 3


@needs_fixtures
@pytest.mark.skipif(
    not (FIXTURES / "orca.hess").is_file(), reason="no orca.hess fixture"
)
def test_real_hessian_is_parsed():
    values = parse_hessian((FIXTURES / "orca.hess").read_text(encoding="utf-8"))
    matrix = values["hessian"]
    assert matrix.shape[0] == matrix.shape[1]
    assert np.allclose(matrix, matrix.T, atol=1e-6)
