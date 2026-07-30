from __future__ import annotations

from pathlib import Path

from atomic_povray import (
    BondRule,
    CutoffPlane,
    DisplayBounds,
    build_geometry,
    load_structure,
)


def test_realistic_hematite_example_builds_consistent_geometry():
    path = Path(__file__).parent / "data" / "fe2o3-012-3x3-unrelaxed.vasp"
    structure = load_structure(path)
    geometry = build_geometry(
        structure,
        bounds=DisplayBounds(
            fractional_ranges=((-1.0, 1.0), (0.0, 1.0), (0.0, 1.0)),
            cutoff_planes=(CutoffPlane((0.0, 0.0, -1.0), -17.0),),
        ),
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
