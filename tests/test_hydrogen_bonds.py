from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from atomic_povray import (
    AtomStyle,
    BondRule,
    BondStyle,
    Color,
    CylinderPrimitive,
    StyleConfig,
    apply_styles,
    build_geometry,
    load_structure,
)


DATA_PATH = Path(__file__).parent / "data" / "rh-h2o-hematite.vasp"
BOND_RULES = (
    BondRule("O", "H", 0.1, 1.2, name="covalent-O-H"),
    BondRule("O", "H", 1.2, 2.0, name="hydrogen-O-H"),
)


@pytest.fixture(scope="module")
def hydrated_hematite_geometry():
    return build_geometry(load_structure(DATA_PATH), bond_rules=BOND_RULES)


def test_hydrated_hematite_distinguishes_oh_bond_types(
    hydrated_hematite_geometry,
):
    geometry = hydrated_hematite_geometry
    bond_counts = Counter(bond.rule_id for bond in geometry.bonds)

    assert Counter(geometry.structure.atoms.get_chemical_symbols()) == {
        "Rh": 2,
        "H": 48,
        "O": 240,
        "Fe": 144,
    }
    assert bond_counts == {
        "covalent-O-H": 48,
        "hydrogen-O-H": 30,
    }

    covalent_distances = [
        bond.distance for bond in geometry.bonds if bond.rule_id == "covalent-O-H"
    ]
    hydrogen_bond_distances = [
        bond.distance for bond in geometry.bonds if bond.rule_id == "hydrogen-O-H"
    ]
    assert min(covalent_distances) == pytest.approx(0.97047299)
    assert max(covalent_distances) == pytest.approx(1.02126413)
    assert min(hydrogen_bond_distances) == pytest.approx(1.60062734)
    assert max(hydrogen_bond_distances) == pytest.approx(1.84123713)


def test_hydrogen_bonds_resolve_to_single_color_dashes(
    hydrated_hematite_geometry,
):
    hydrogen_bond_color = Color(0.23, 0.47, 0.71)
    styled = apply_styles(
        hydrated_hematite_geometry,
        StyleConfig(
            elements={
                "O": AtomStyle(0.4, Color(0.9, 0.1, 0.1)),
                "H": AtomStyle(0.2, Color(0.9, 0.9, 0.9)),
            },
            bonds={
                "covalent-O-H": BondStyle(radius=0.07),
                "hydrogen-O-H": BondStyle(
                    radius=0.04,
                    color=hydrogen_bond_color,
                    style="dashed",
                    dashes=4,
                ),
            },
        ),
    )
    hydrogen_bond_dashes = [
        primitive
        for primitive in styled.primitives
        if isinstance(primitive, CylinderPrimitive)
        and primitive.material.color == hydrogen_bond_color
    ]

    assert len(hydrogen_bond_dashes) == 30 * 4
    assert all(dash.radius == 0.04 for dash in hydrogen_bond_dashes)
