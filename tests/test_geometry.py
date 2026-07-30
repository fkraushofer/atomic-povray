from __future__ import annotations

import numpy as np
import pytest
from ase import Atoms

from atomic_povray import (
    BondRule,
    CutoffPlane,
    DisplayBounds,
    StructureModel,
    build_geometry,
)


def model(atoms: Atoms) -> StructureModel:
    return StructureModel(atoms)


def test_float_fractional_ranges_combine_replication_crop_and_offset():
    atoms = Atoms(
        "FeO",
        scaled_positions=((0.25, 0.5, 0.5), (0.75, 0.5, 0.5)),
        cell=(4.0, 4.0, 4.0),
        pbc=True,
    )
    geometry = build_geometry(
        model(atoms),
        bounds=DisplayBounds(
            fractional_ranges=((-0.5, 1.5), (0.0, 1.0), (0.0, 1.0))
        ),
    )

    assert [atom.fractional_position[0] for atom in geometry.atoms] == pytest.approx(
        [-0.25, 0.25, 0.75, 1.25]
    )
    assert {atom.key.image_shift[0] for atom in geometry.atoms} == {-1, 0, 1}


def test_cartesian_cutoff_plane_uses_normal_and_origin_distance():
    atoms = Atoms(
        "FeO",
        positions=((0.5, 0.0, 0.0), (1.5, 0.0, 0.0)),
        cell=(2.0, 2.0, 2.0),
        pbc=False,
    )
    geometry = build_geometry(
        model(atoms),
        bounds=DisplayBounds(
            cutoff_planes=(CutoffPlane(normal=(2.0, 0.0, 0.0), distance=1.0),)
        ),
    )

    assert [atom.symbol for atom in geometry.primary_atoms] == ["Fe"]


def test_display_range_face_can_forbid_bond_extensions():
    atoms = Atoms(
        "FeO",
        scaled_positions=((0.9, 0.5, 0.5), (0.1, 0.5, 0.5)),
        cell=(10.0, 10.0, 10.0),
        pbc=True,
    )
    allowed = build_geometry(
        model(atoms),
        bounds=DisplayBounds(),
        bond_rules=(BondRule("Fe", "O", 0.5, 2.5),),
    )
    forbidden = build_geometry(
        model(atoms),
        bounds=DisplayBounds(
            upper_allow_bond_extensions=(False, True, True),
        ),
        bond_rules=(BondRule("Fe", "O", 0.5, 2.5),),
    )

    assert len(allowed.extension_atoms) == 1
    assert len(allowed.bonds) == 1
    assert forbidden.extension_atoms == ()
    assert forbidden.bonds == ()


def test_cutoff_plane_can_forbid_bond_extensions():
    atoms = Atoms(
        "FeO",
        positions=((0.5, 0.0, 0.0), (1.5, 0.0, 0.0)),
        cell=(2.0, 2.0, 2.0),
        pbc=False,
    )
    geometry = build_geometry(
        model(atoms),
        bounds=DisplayBounds(
            cutoff_planes=(
                CutoffPlane(
                    normal=(1.0, 0.0, 0.0),
                    distance=1.0,
                    allow_bond_extensions=False,
                ),
            )
        ),
        bond_rules=(BondRule("Fe", "O", 0.5, 1.5),),
    )

    assert [atom.symbol for atom in geometry.atoms] == ["Fe"]
    assert geometry.bonds == ()


def test_periodic_bond_is_instantiated_across_internal_replica_boundary():
    atoms = Atoms(
        "FeO",
        scaled_positions=((0.95, 0.5, 0.5), (0.05, 0.5, 0.5)),
        cell=(10.0, 10.0, 10.0),
        pbc=True,
    )
    geometry = build_geometry(
        model(atoms),
        bounds=DisplayBounds(
            fractional_ranges=((-1.0, 1.0), (0.0, 1.0), (0.0, 1.0)),
            lower_allow_bond_extensions=(False, False, False),
            upper_allow_bond_extensions=(False, False, False),
        ),
        bond_rules=(BondRule("O", "Fe", 0.5, 1.5),),
    )

    assert len(geometry.atoms) == 4
    assert len(geometry.bonds) == 1
    bond = geometry.bonds[0]
    assert bond.distance == pytest.approx(1.0)
    assert bond.atom_a.image_shift != bond.atom_b.image_shift
    assert geometry.coordination(bond.atom_a) == 1
    assert geometry.coordination(bond.atom_b) == 1


def test_bond_search_handles_a_skewed_periodic_cell():
    cell = np.array(((4.0, 0.0, 0.0), (1.5, 3.5, 0.0), (0.0, 0.0, 8.0)))
    atoms = Atoms(
        "FeO",
        scaled_positions=((0.95, 0.95, 0.5), (0.05, 0.05, 0.5)),
        cell=cell,
        pbc=True,
    )
    expected = np.linalg.norm(np.array((0.1, 0.1, 0.0)) @ cell)
    geometry = build_geometry(
        model(atoms),
        bounds=DisplayBounds(
            fractional_ranges=((0.0, 2.0), (0.0, 2.0), (0.0, 1.0))
        ),
        bond_rules=(BondRule("Fe", "O", 0.1, 1.0),),
    )

    assert geometry.bonds
    assert all(bond.distance == pytest.approx(expected) for bond in geometry.bonds)
    assert any(
        bond.atom_a.image_shift != bond.atom_b.image_shift for bond in geometry.bonds
    )


def test_cartesian_z_bounds_remove_atoms_and_incident_bonds():
    atoms = Atoms(
        "FeO",
        positions=((0.0, 0.0, 1.0), (0.0, 0.0, 2.0)),
        cell=(10.0, 10.0, 10.0),
        pbc=False,
    )
    geometry = build_geometry(
        model(atoms),
        bounds=DisplayBounds(
            cutoff_planes=(CutoffPlane((0.0, 0.0, -1.0), -1.5),)
        ),
        bond_rules=(BondRule("Fe", "O", 0.5, 1.5),),
    )

    assert [atom.symbol for atom in geometry.atoms] == ["O"]
    assert geometry.bonds == ()


def test_reversed_element_order_matches_the_same_rule():
    atoms = Atoms(
        "OFe",
        positions=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
        cell=(10.0, 10.0, 10.0),
        pbc=False,
    )
    geometry = build_geometry(
        model(atoms),
        bond_rules=(BondRule("Fe", "O", 0.5, 1.5, name="metal-oxygen"),),
    )
    assert len(geometry.bonds) == 1
    assert geometry.bonds[0].rule_id == "metal-oxygen"


def test_asymmetric_rule_adds_only_element_b_as_an_extension():
    atoms = Atoms(
        "FeO",
        positions=((0.0, 0.0, 2.0), (0.0, 0.0, 1.0)),
        cell=(10.0, 10.0, 10.0),
        pbc=False,
    )
    geometry = build_geometry(
        model(atoms),
        bounds=DisplayBounds(
            cutoff_planes=(CutoffPlane((0.0, 0.0, -1.0), -1.5),)
        ),
        bond_rules=(BondRule("Fe", "O", 0.5, 1.5),),
    )

    assert [atom.symbol for atom in geometry.atoms] == ["Fe", "O"]
    assert [atom.is_extension for atom in geometry.atoms] == [False, True]
    assert len(geometry.bonds) == 1

    reverse_rule = build_geometry(
        model(atoms),
        bounds=DisplayBounds(
            cutoff_planes=(CutoffPlane((0.0, 0.0, -1.0), -1.5),)
        ),
        bond_rules=(BondRule("O", "Fe", 0.5, 1.5),),
    )
    assert [atom.symbol for atom in reverse_rule.atoms] == ["Fe"]
    assert reverse_rule.bonds == ()


def test_symmetric_extension_mode_searches_from_either_element():
    atoms = Atoms(
        "FeO",
        positions=((0.0, 0.0, 1.0), (0.0, 0.0, 2.0)),
        cell=(10.0, 10.0, 10.0),
        pbc=False,
    )
    geometry = build_geometry(
        model(atoms),
        bounds=DisplayBounds(
            cutoff_planes=(CutoffPlane((0.0, 0.0, -1.0), -1.5),)
        ),
        bond_rules=(BondRule("Fe", "O", 0.5, 1.5, extension_mode="symmetric"),),
    )

    assert [atom.symbol for atom in geometry.atoms] == ["O", "Fe"]
    assert geometry.atoms[1].is_extension
    assert len(geometry.bonds) == 1


def test_extension_atom_never_seeds_a_second_extension():
    atoms = Atoms(
        "FeOFe",
        positions=((0.0, 0.0, 2.0), (0.0, 0.0, 1.0), (0.0, 0.0, 0.0)),
        cell=(10.0, 10.0, 10.0),
        pbc=False,
    )
    geometry = build_geometry(
        model(atoms),
        bounds=DisplayBounds(
            cutoff_planes=(CutoffPlane((0.0, 0.0, -1.0), -1.5),)
        ),
        bond_rules=(BondRule("Fe", "O", 0.5, 1.5, extension_mode="symmetric"),),
    )

    assert [atom.symbol for atom in geometry.atoms] == ["Fe", "O"]
    assert len(geometry.bonds) == 1
    assert all(atom.key.source_index != 2 for atom in geometry.atoms)


def test_a_plane_can_forbid_bond_extensions():
    atoms = Atoms(
        "FeO",
        positions=((0.0, 0.0, 2.0), (0.0, 0.0, 1.0)),
        cell=(10.0, 10.0, 10.0),
        pbc=False,
    )
    geometry = build_geometry(
        model(atoms),
        bounds=DisplayBounds(
            cutoff_planes=(
                CutoffPlane(
                    (0.0, 0.0, -1.0),
                    -1.5,
                    allow_bond_extensions=False,
                ),
            ),
        ),
        bond_rules=(BondRule("Fe", "O", 0.5, 1.5),),
    )

    assert [atom.symbol for atom in geometry.atoms] == ["Fe"]
    assert geometry.bonds == ()


def test_fractional_range_uses_the_same_extension_policy():
    atoms = Atoms(
        "FeO",
        scaled_positions=((0.6, 0.5, 0.5), (0.4, 0.5, 0.5)),
        cell=(5.0, 5.0, 5.0),
        pbc=False,
    )
    bounds = DisplayBounds(
        fractional_ranges=((0.5, 1.0), (0.0, 1.0), (0.0, 1.0))
    )
    geometry = build_geometry(
        model(atoms),
        bounds=bounds,
        bond_rules=(BondRule("Fe", "O", 0.5, 1.5),),
    )

    assert len(geometry.atoms) == 2
    assert geometry.atoms[1].is_extension
    assert len(geometry.bonds) == 1


def test_replication_faces_follow_the_same_extension_policy():
    atoms = Atoms(
        "FeO",
        scaled_positions=((0.95, 0.5, 0.5), (0.05, 0.5, 0.5)),
        cell=(10.0, 10.0, 10.0),
        pbc=True,
    )
    default_geometry = build_geometry(
        model(atoms),
        bond_rules=(BondRule("Fe", "O", 0.5, 1.5),),
    )
    clipped_geometry = build_geometry(
        model(atoms),
        bounds=DisplayBounds(
            upper_allow_bond_extensions=(False, True, True)
        ),
        bond_rules=(BondRule("Fe", "O", 0.5, 1.5),),
    )

    assert len(default_geometry.atoms) == 3
    assert sum(atom.is_extension for atom in default_geometry.atoms) == 1
    assert len(default_geometry.bonds) == 1
    assert len(clipped_geometry.atoms) == 2
    assert clipped_geometry.bonds == ()
