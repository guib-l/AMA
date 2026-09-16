"""Tests of the DFTB+ parsers: synthetic extracts, then the real fixtures.

The fixture tests are skipped until real DFTB+ outputs are placed in
``test/fixtures/dftbplus/``; they need no DFTB+ installation, only its files.
"""

from pathlib import Path

import numpy as np
import pytest
from ase.units import Hartree

from amac.assets.dftbplus.parser import (
    DftbPlusOutput,
    parse_band_out,
    parse_detailed_out,
    parse_directory,
    parse_excitations,
    parse_matrix,
    parse_md_out,
    parse_results_tag,
    parse_tagged,
)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "dftbplus"
needs_fixtures = pytest.mark.skipif(
    not FIXTURES.is_dir(), reason=f"no real DFTB+ outputs in {FIXTURES}"
)

RESULTS_TAG = """\
total_energy         :real:0:
 -0.403413813117E+001
forces               :real:2:3,2
  0.100000000000E+000  0.200000000000E+000  0.300000000000E+000
 -0.100000000000E+000 -0.200000000000E+000 -0.300000000000E+000
gross_atomic_charges :real:1:2
 -0.600000000000E+000  0.600000000000E+000
fermi_level          :real:0:
 -0.200000000000E+000
"""

DETAILED_OUT = """\
 Total energy:                      -4.5000000000 H        -122.4490 eV
 Band energy:                       -2.5000000000 H         -68.0281 eV
 Fermi level:                       -0.2000000000 H          -5.4422 eV
 SCC converged

 Total Forces
    1      0.100000000000      0.200000000000      0.300000000000
    2     -0.100000000000     -0.200000000000     -0.300000000000

 Net atomic charges (e)
 Atom         Netcharge
    1        -0.60000000
    2         0.60000000

 Dipole moment:    0.00000000    0.00000000    0.50000000 au
"""

BAND_OUT = """\
KPT            1  SPIN            1  KWEIGHT    1.0000000000
   1   -13.605693    2.00000
   2    -9.000000    0.00000
"""


def test_parse_tagged_reads_names_ranks_and_shapes():
    blocks = parse_tagged(RESULTS_TAG)
    assert sorted(blocks) == ["fermi_level", "forces", "gross_atomic_charges", "total_energy"]
    assert blocks["total_energy"] == pytest.approx(-4.03413813117)
    assert blocks["forces"].shape == (2, 3)
    assert blocks["gross_atomic_charges"].tolist() == [-0.6, 0.6]


def test_parse_tagged_rejects_a_truncated_block():
    with pytest.raises(ValueError, match="expected 6 values, got 3"):
        parse_tagged("forces:real:2:3,2\n 1.0 2.0 3.0\n")


def test_parse_results_tag_uses_the_dataclass_names():
    values = parse_results_tag(RESULTS_TAG)
    assert values["energy"] == pytest.approx(-4.03413813117)
    assert values["forces"][0].tolist() == [0.1, 0.2, 0.3]
    assert values["charges"].tolist() == [-0.6, 0.6]
    assert values["fermi_level"] == pytest.approx(-0.2)
    assert DftbPlusOutput(**values).energy == pytest.approx(-4.03413813117)


def test_parse_detailed_out_reads_energies_tables_and_convergence():
    values = parse_detailed_out(DETAILED_OUT)
    assert values["energy"] == pytest.approx(-4.5)
    assert values["band_energy"] == pytest.approx(-2.5)
    assert values["fermi_level"] == pytest.approx(-0.2)
    assert values["converged"] is True
    assert values["forces"].shape == (2, 3)
    assert values["charges"].tolist() == [-0.6, 0.6]
    assert values["dipole"].tolist() == [0.0, 0.0, 0.5]
    assert DftbPlusOutput(**values).converged is True


def test_parse_band_out_returns_eigenvalues_and_occupations():
    energies, occupations = parse_band_out(BAND_OUT)
    assert energies.shape == occupations.shape == (1, 2)
    assert energies[0].tolist() == [-13.605693, -9.0]
    assert occupations[0].tolist() == [2.0, 0.0]


def test_parse_matrix_and_md_out_and_excitations():
    assert parse_matrix("1.0 2.0\n3.0 4.0\n").tolist() == [1.0, 2.0, 3.0, 4.0]
    assert parse_matrix("\n") is None
    steps = parse_md_out(" MD Kinetic Energy:   0.1\n MD Kinetic Energy:   0.2\n")
    assert steps["MD Kinetic Energy"].tolist() == [0.1, 0.2]
    excitations = parse_excitations("w [eV]   Osc.\n 2.0   0.5\n 3.0   0.1\n")
    assert excitations.tolist() == [[2.0, 0.5], [3.0, 0.1]]


def test_parse_directory_prefers_results_tag_and_lists_the_files(tmp_path):
    (tmp_path / "detailed.out").write_text(DETAILED_OUT, encoding="utf-8")
    (tmp_path / "results.tag").write_text(RESULTS_TAG, encoding="utf-8")
    output = parse_directory(tmp_path)
    # detailed.out gives -4.5, results.tag -4.034: the machine-readable file wins.
    assert output.energy == pytest.approx(-4.03413813117)
    assert output.converged is True
    assert output.files == ("detailed.out", "results.tag")
    assert output.eigenvalues is None


def test_parse_directory_converts_band_out_to_hartree(tmp_path):
    (tmp_path / "band.out").write_text(BAND_OUT, encoding="utf-8")
    output = parse_directory(tmp_path)
    assert output.eigenvalues[0][0] == pytest.approx(-13.605693 / Hartree)
    assert output.occupations[0].tolist() == [2.0, 0.0]


def test_parse_directory_reads_the_final_geometry(tmp_path):
    (tmp_path / "geo_end.gen").write_text(
        "2  C\n H\n 1 1 0.0 0.0 0.0\n 2 1 0.0 0.0 0.74\n", encoding="utf-8"
    )
    output = parse_directory(tmp_path)
    assert output.final_geometry.get_chemical_symbols() == ["H", "H"]
    assert output.final_geometry.positions[1][2] == pytest.approx(0.74)


def test_parse_directory_of_an_empty_run(tmp_path):
    assert parse_directory(tmp_path) == DftbPlusOutput()


@needs_fixtures
@pytest.mark.parametrize(
    "name",
    [
        "results.tag",
        "detailed.out",
        "band.out",
        "hessian.out",
        "born.out",
        "md.out",
        "EXC.DAT",
        "geo_end.gen",
    ],
)
def test_real_output_file_is_read(name):
    """Each real output file is parsed, and gives at least one value."""
    path = FIXTURES / name
    if not path.is_file():
        pytest.skip(f"{name} is not among the provided fixtures")
    output = parse_directory(FIXTURES)
    assert name in output.files
    assert any(
        value is not None and not isinstance(value, tuple)
        for value in vars(output).values()
    )


@needs_fixtures
def test_real_run_gives_energy_and_forces():
    output = parse_directory(FIXTURES)
    assert output.energy is not None
    if output.forces is not None:
        forces = np.asarray(output.forces)
        assert forces.ndim == 2 and forces.shape[1] == 3
