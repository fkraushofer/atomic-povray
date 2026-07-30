from __future__ import annotations

from pathlib import Path

from atomic_povray import BondRule, CartesianBounds, build_geometry, load_structure


def test_realistic_hematite_example_builds_consistent_geometry():
    path = Path(__file__).parent / "data" / "hematite_1x1_unrelaxed_bare.vasp"
    structure = load_structure(path)
    geometry = build_geometry(
        structure,
        repetitions=(2, 1, 1),
        bounds=CartesianBounds(z_min=17.0),
        bond_rules=(BondRule("Fe", "O", 0.1, 2.45),),
    )

    assert len(structure.atoms) == 360
    assert len(geometry.primary_atoms) == 432
    assert len(geometry.extension_atoms) == 151
    assert len(geometry.atoms) == 583
    assert len(geometry.bonds) == 1044
    assert all(atom.position[2] >= 17.0 for atom in geometry.primary_atoms)
    assert all(atom.symbol == "O" for atom in geometry.extension_atoms)
    assert all(0.1 <= bond.distance <= 2.45 for bond in geometry.bonds)
    assert all(
        geometry.coordination(index) == len(geometry.adjacency[index])
        for index in range(len(geometry.atoms))
    )
