from __future__ import annotations

import numpy as np
import pytest
from ase import Atoms

from atomic_povray import (
    BondRule,
    BoundaryPlane,
    BoundarySet,
    CartesianBounds,
    ReplicationConfig,
    StructureModel,
    build_geometry,
    centered_image_shifts,
)


def model(atoms: Atoms) -> StructureModel:
    return StructureModel(atoms)


def test_centered_replication_shifts_match_legacy_convention():
    assert centered_image_shifts((1, 1, 1)) == ((0, 0, 0),)
    assert centered_image_shifts((2, 1, 1)) == ((-1, 0, 0), (0, 0, 0))
    assert centered_image_shifts((3, 1, 1)) == (
        (-1, 0, 0),
        (0, 0, 0),
        (1, 0, 0),
    )


def test_periodic_bond_is_instantiated_across_internal_replica_boundary():
    atoms = Atoms(
        "FeO",
        scaled_positions=((0.95, 0.5, 0.5), (0.05, 0.5, 0.5)),
        cell=(10.0, 10.0, 10.0),
        pbc=True,
    )
    geometry = build_geometry(
        model(atoms),
        repetitions=ReplicationConfig(
            (2, 1, 1),
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
        repetitions=(2, 2, 1),
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
        bounds=CartesianBounds(z_min=1.5),
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
        bounds=CartesianBounds(z_min=1.5),
        bond_rules=(BondRule("Fe", "O", 0.5, 1.5),),
    )

    assert [atom.symbol for atom in geometry.atoms] == ["Fe", "O"]
    assert [atom.is_extension for atom in geometry.atoms] == [False, True]
    assert len(geometry.bonds) == 1

    reverse_rule = build_geometry(
        model(atoms),
        bounds=CartesianBounds(z_min=1.5),
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
        bounds=CartesianBounds(z_min=1.5),
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
        bounds=CartesianBounds(z_min=1.5),
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
        bounds=CartesianBounds(
            z_min=1.5,
            z_min_allow_bond_extensions=False,
        ),
        bond_rules=(BondRule("Fe", "O", 0.5, 1.5),),
    )

    assert [atom.symbol for atom in geometry.atoms] == ["Fe"]
    assert geometry.bonds == ()


def test_arbitrary_fractional_plane_uses_the_same_extension_policy():
    atoms = Atoms(
        "FeO",
        scaled_positions=((0.6, 0.5, 0.5), (0.4, 0.5, 0.5)),
        cell=(5.0, 5.0, 5.0),
        pbc=False,
    )
    bounds = BoundarySet(
        (
            BoundaryPlane(
                (1.0, 0.0, 0.0),
                0.5,
                coordinate_space="fractional",
                allow_bond_extensions=True,
            ),
        )
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
        repetitions=ReplicationConfig(upper_allow_bond_extensions=(False, True, True)),
        bond_rules=(BondRule("Fe", "O", 0.5, 1.5),),
    )

    assert len(default_geometry.atoms) == 3
    assert sum(atom.is_extension for atom in default_geometry.atoms) == 1
    assert len(default_geometry.bonds) == 1
    assert len(clipped_geometry.atoms) == 2
    assert clipped_geometry.bonds == ()
