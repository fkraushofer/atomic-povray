from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from ase import Atoms

from atomic_povray import (
    AtomKey,
    AtomSelectionRule,
    AtomStyle,
    AtomStyleOverride,
    BondRule,
    BondStyle,
    Color,
    CoordinationStyleRule,
    CutoffPlane,
    CylinderPrimitive,
    DisplayBounds,
    SpherePrimitive,
    StructureModel,
    StyleConfig,
    apply_styles,
    build_geometry,
    load_structure,
    resolve_atom_styles,
)


DATA_PATH = Path(__file__).parent / "data" / "rh-h2o-hematite.vasp"


def test_coordination_rule_uses_complete_environment_across_crop_boundary():
    atoms = Atoms(
        "FeO4",
        positions=(
            (5.0, 5.0, 5.0),
            (6.0, 5.0, 5.0),
            (4.0, 5.0, 5.0),
            (5.0, 6.0, 5.0),
            (5.0, 4.0, 5.0),
        ),
        cell=(10.0, 10.0, 10.0),
        pbc=False,
    )
    geometry = build_geometry(
        StructureModel(atoms),
        bounds=DisplayBounds(
            cutoff_planes=(
                CutoffPlane(
                    normal=(1.0, 0.0, 0.0),
                    distance=5.5,
                    allow_bond_extensions=False,
                ),
            )
        ),
        bond_rules=(BondRule("Fe", "O", 0.5, 1.5),),
    )
    tetrahedral = Color(0.2, 0.4, 0.8)
    styles = resolve_atom_styles(
        geometry,
        StyleConfig(
            elements={"Fe": AtomStyle(0.5, Color(0.8, 0.2, 0.2))},
            coordination_rules=(
                CoordinationStyleRule(
                    element="Fe",
                    coordination=4,
                    neighbor_elements={"O"},
                    bond_rules={"Fe-O"},
                    style=AtomStyleOverride(color=tetrahedral),
                ),
            ),
        ),
    )

    assert len(geometry.atoms) == 4
    assert geometry.coordination(AtomKey(0)) == 3
    assert len(geometry.source_environments[0]) == 4
    assert styles[AtomKey(0)].color == tetrahedral


def test_rule_precedence_and_later_rules_apply_partial_overrides():
    atoms = Atoms(
        "FeO4",
        positions=(
            (5.0, 5.0, 5.0),
            (6.0, 5.0, 5.0),
            (4.0, 5.0, 5.0),
            (5.0, 6.0, 5.0),
            (5.0, 4.0, 5.0),
        ),
        cell=(10.0, 10.0, 10.0),
        pbc=False,
    )
    geometry = build_geometry(
        StructureModel(atoms),
        bond_rules=(BondRule("Fe", "O", 0.5, 1.5),),
    )
    resolved = resolve_atom_styles(
        geometry,
        StyleConfig(
            elements={"Fe": AtomStyle(0.5, Color(0.1, 0.1, 0.1))},
            coordination_rules=(
                CoordinationStyleRule(
                    "Fe",
                    4,
                    AtomStyleOverride(color=Color(0.2, 0.2, 0.2)),
                ),
            ),
            selection_rules=(
                AtomSelectionRule(
                    lambda selected: [0],
                    AtomStyleOverride(color=Color(0.3, 0.3, 0.3), radius=0.6),
                ),
                AtomSelectionRule(
                    lambda selected: np.array(
                        [True, False, False, False, False]
                    ),
                    AtomStyleOverride(radius=0.7),
                ),
            ),
            source_atom_overrides={
                0: AtomStyleOverride(color=Color(0.4, 0.4, 0.4))
            },
            atom_instance_overrides={
                AtomKey(0): AtomStyleOverride(color=Color(0.5, 0.5, 0.5))
            },
        ),
    )

    assert resolved[AtomKey(0)].color == Color(0.5, 0.5, 0.5)
    assert resolved[AtomKey(0)].radius == pytest.approx(0.7)


def test_source_override_reaches_replicas_but_instance_override_is_specific():
    atoms = Atoms(
        "Fe",
        scaled_positions=((0.5, 0.5, 0.5),),
        cell=(2.0, 2.0, 2.0),
        pbc=True,
    )
    geometry = build_geometry(
        StructureModel(atoms),
        bounds=DisplayBounds(
            fractional_ranges=((0.0, 2.0), (0.0, 1.0), (0.0, 1.0))
        ),
    )
    common = Color(0.2, 0.3, 0.4)
    special = Color(0.8, 0.7, 0.6)
    resolved = resolve_atom_styles(
        geometry,
        StyleConfig(
            source_atom_overrides={0: AtomStyleOverride(color=common)},
            atom_instance_overrides={
                AtomKey(0, (1, 0, 0)): AtomStyleOverride(color=special)
            },
        ),
    )

    assert resolved[AtomKey(0, (0, 0, 0))].color == common
    assert resolved[AtomKey(0, (1, 0, 0))].color == special


def test_visibility_removes_atom_and_incident_bond_primitives():
    atoms = Atoms(
        "FeO",
        positions=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
        cell=(10.0, 10.0, 10.0),
        pbc=False,
    )
    geometry = build_geometry(
        StructureModel(atoms),
        bond_rules=(BondRule("Fe", "O", 0.5, 1.5),),
    )
    styled = apply_styles(
        geometry,
        StyleConfig(
            selection_rules=(
                AtomSelectionRule(
                    lambda selected: [1],
                    AtomStyleOverride(visible=False),
                ),
            )
        ),
    )

    assert sum(isinstance(item, SpherePrimitive) for item in styled.primitives) == 1
    assert not any(
        isinstance(item, CylinderPrimitive) for item in styled.primitives
    )


def test_selected_endpoint_colors_split_dashed_bonds():
    atoms = Atoms(
        "OH",
        positions=((0.0, 0.0, 0.0), (1.8, 0.0, 0.0)),
        cell=(10.0, 10.0, 10.0),
        pbc=False,
    )
    geometry = build_geometry(
        StructureModel(atoms),
        bond_rules=(BondRule("O", "H", 1.0, 2.0),),
    )
    selected_color = Color(0.1, 0.8, 0.2)
    styled = apply_styles(
        geometry,
        StyleConfig(
            elements={
                "O": AtomStyle(0.4, Color(0.8, 0.1, 0.1)),
                "H": AtomStyle(0.2, Color(0.9, 0.9, 0.9)),
            },
            selection_rules=(
                AtomSelectionRule(
                    lambda selected: [0],
                    AtomStyleOverride(color=selected_color),
                ),
            ),
            bonds={"O-H": BondStyle(style="dashed", dashes=2)},
        ),
    )
    cylinders = [
        item for item in styled.primitives if isinstance(item, CylinderPrimitive)
    ]

    assert cylinders
    assert cylinders[0].material.color == selected_color


def test_real_structure_selects_twelve_oxygen_atoms_above_z_26():
    structure = load_structure(DATA_PATH)
    selected_color = Color(0.12, 0.34, 0.56)
    geometry = build_geometry(structure)
    resolved = resolve_atom_styles(
        geometry,
        StyleConfig(
            elements={"O": AtomStyle(0.4, Color(0.9, 0.1, 0.1))},
            selection_rules=(
                AtomSelectionRule(
                    lambda atoms: (
                        (np.asarray(atoms.get_chemical_symbols()) == "O")
                        & (atoms.positions[:, 2] > 26.0)
                    ),
                    AtomStyleOverride(color=selected_color),
                ),
            ),
        ),
    )
    selected = [
        atom
        for atom in geometry.atoms
        if atom.symbol == "O" and resolved[atom.key].color == selected_color
    ]

    assert len(selected) == 12
    assert all(atom.position[2] > 26.0 for atom in selected)


@pytest.mark.parametrize(
    ("selector", "exception", "message"),
    (
        (lambda atoms: np.array([True]), ValueError, "shape"),
        (lambda atoms: [len(atoms)], IndexError, "indices"),
        (lambda atoms: [0.5], TypeError, "integer"),
    ),
)
def test_invalid_selection_results_raise_clear_errors(selector, exception, message):
    geometry = build_geometry(
        StructureModel(
            Atoms(
                "FeO",
                positions=((0.0, 0.0, 0.0), (1.0, 0.0, 0.0)),
                cell=(10.0, 10.0, 10.0),
                pbc=False,
            )
        )
    )
    with pytest.raises(exception, match=message):
        resolve_atom_styles(
            geometry,
            StyleConfig(
                selection_rules=(
                    AtomSelectionRule(selector, AtomStyleOverride(radius=0.5)),
                )
            ),
        )
