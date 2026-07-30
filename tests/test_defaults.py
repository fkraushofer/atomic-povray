from __future__ import annotations

import pytest
from ase import Atoms
from ase.data import atomic_numbers, covalent_radii
from ase.data.colors import jmol_colors

from atomic_povray import (
    AtomStyle,
    BondRule,
    BondRuleSet,
    Color,
    StructureModel,
    StyleConfig,
    apply_styles,
    build_geometry,
    get_default_bonds,
)
from atomic_povray.primitives import CylinderPrimitive, SpherePrimitive


def test_atom_style_uses_ase_radius_and_color_by_default():
    style = StyleConfig().atom_style("O")
    oxygen = atomic_numbers["O"]

    assert style.radius == pytest.approx(covalent_radii[oxygen])
    assert style.color.as_tuple()[:3] == pytest.approx(jmol_colors[oxygen])


def test_empty_style_config_uses_ball_and_stick_defaults():
    styles = StyleConfig()

    assert styles.preset_style == "ball_and_stick"
    assert styles.atom_size_scale == pytest.approx(0.5)
    assert styles.draw_bonds
    assert styles.atom_finish.phong == pytest.approx(0.3)
    assert styles.bond_finish.phong == pytest.approx(0.0)
    assert styles.default_bond.radius == pytest.approx(0.10)


def test_style_presets_control_rendered_atom_scale_and_bond_visibility():
    atoms = Atoms(
        "FeO",
        positions=((0.0, 0.0, 0.0), (1.8, 0.0, 0.0)),
        cell=(10.0, 10.0, 10.0),
        pbc=False,
    )
    geometry = build_geometry(StructureModel(atoms))
    ball_and_stick = apply_styles(geometry, StyleConfig())
    space_filling = apply_styles(
        geometry,
        StyleConfig(preset_style="space_filling"),
    )

    ball_spheres = [
        primitive
        for primitive in ball_and_stick.primitives
        if isinstance(primitive, SpherePrimitive)
    ]
    space_spheres = [
        primitive
        for primitive in space_filling.primitives
        if isinstance(primitive, SpherePrimitive)
    ]

    expected_radii = [
        covalent_radii[atomic_numbers[symbol]]
        for symbol in atoms.get_chemical_symbols()
    ]
    assert [sphere.radius for sphere in ball_spheres] == pytest.approx(
        [0.5 * radius for radius in expected_radii]
    )
    assert [sphere.radius for sphere in space_spheres] == pytest.approx(
        expected_radii
    )
    assert any(
        isinstance(primitive, CylinderPrimitive)
        for primitive in ball_and_stick.primitives
    )
    assert not any(
        isinstance(primitive, CylinderPrimitive)
        for primitive in space_filling.primitives
    )


def test_explicit_atom_size_scale_overrides_preset_and_scales_custom_radii():
    atoms = Atoms(
        "O",
        positions=((0.0, 0.0, 0.0),),
        cell=(10.0, 10.0, 10.0),
        pbc=False,
    )
    styled = apply_styles(
        build_geometry(StructureModel(atoms), bond_rules=()),
        StyleConfig(
            preset_style="space_filling",
            atom_size_scale=0.75,
            elements={"O": AtomStyle(radius=0.4)},
        ),
    )
    sphere = next(
        primitive
        for primitive in styled.primitives
        if isinstance(primitive, SpherePrimitive)
    )

    assert sphere.radius == pytest.approx(0.3)


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"preset_style": "wireframe"}, ValueError),
        ({"atom_size_scale": 0.0}, ValueError),
        ({"atom_size_scale": float("inf")}, ValueError),
        ({"atom_size_scale": True}, TypeError),
    ],
)
def test_style_preset_validation(kwargs, error):
    with pytest.raises(error):
        StyleConfig(**kwargs)


def test_partial_element_style_keeps_unspecified_ase_default():
    custom_color = Color(0.1, 0.2, 0.3)
    color_only = StyleConfig(
        elements={"Fe": AtomStyle(color=custom_color)}
    ).atom_style("Fe")
    radius_only = StyleConfig(
        elements={"O": AtomStyle(radius=0.4)}
    ).atom_style("O")

    assert color_only.color == custom_color
    assert color_only.radius == pytest.approx(
        covalent_radii[atomic_numbers["Fe"]]
    )
    assert radius_only.radius == pytest.approx(0.4)
    assert radius_only.color.as_tuple()[:3] == pytest.approx(
        jmol_colors[atomic_numbers["O"]]
    )


def test_default_bonds_use_curated_pairs_and_metal_to_nonmetal_direction():
    rules = get_default_bonds(Atoms("FeRhOH"))

    assert "default:Fe-Rh" not in rules
    assert rules["default:Fe-O"].element_a == "Fe"
    assert rules["default:Fe-O"].element_b == "O"
    assert rules["default:Rh-O"].element_a == "Rh"
    assert rules["default:Rh-O"].element_b == "O"
    assert rules["default:O-O"].allows_extension_from("O", "O")


def test_build_geometry_uses_default_bonds_when_rules_are_omitted():
    atoms = Atoms(
        "FeO",
        positions=((0.0, 0.0, 0.0), (1.8, 0.0, 0.0)),
        cell=(10.0, 10.0, 10.0),
        pbc=False,
    )

    automatic = build_geometry(StructureModel(atoms))
    disabled = build_geometry(StructureModel(atoms), bond_rules=())
    styled = apply_styles(automatic, StyleConfig())
    cylinders = [
        primitive
        for primitive in styled.primitives
        if isinstance(primitive, CylinderPrimitive)
    ]

    assert len(automatic.bonds) == 1
    assert automatic.bonds[0].rule_id == "default:Fe-O"
    assert disabled.bonds == ()
    assert all(cylinder.radius == pytest.approx(0.10) for cylinder in cylinders)
    assert cylinders[0].material.color != cylinders[1].material.color


def test_bond_scale_controls_ordinary_cutoff():
    small = get_default_bonds(Atoms("FeO"), bond_scale=1.0)
    large = get_default_bonds(Atoms("FeO"), bond_scale=1.3)

    expected_sum = (
        covalent_radii[atomic_numbers["Fe"]]
        + covalent_radii[atomic_numbers["O"]]
    )
    assert small["default:Fe-O"].max_distance == pytest.approx(expected_sum)
    assert large["default:Fe-O"].max_distance == pytest.approx(
        1.3 * expected_sum
    )


def test_oh_defaults_have_adjacent_ranges_and_fixed_hydrogen_limit():
    rules = get_default_bonds(StructureModel(Atoms("OH")), bond_scale=1.2)
    covalent = rules["default:covalent:O-H"]
    hydrogen = rules["default:hydrogen:O-H"]

    assert covalent.max_distance == pytest.approx(hydrogen.min_distance)
    assert hydrogen.max_distance == pytest.approx(2.1)
    assert hydrogen.extension_mode == "none"
    assert StyleConfig().bond_style(hydrogen.rule_id).style == "dashed"


def test_materialized_default_rules_can_be_edited_and_deleted():
    rules = get_default_bonds(Atoms("FeOH"))
    updated = rules.update("default:Fe-O", max_distance=2.5)

    assert isinstance(rules, BondRuleSet)
    assert updated.max_distance == pytest.approx(2.5)
    assert rules["default:Fe-O"].max_distance == pytest.approx(2.5)

    removed = rules.remove_pair("O", "H")
    assert {rule.rule_id for rule in removed} == {
        "default:covalent:O-H",
        "default:hydrogen:O-H",
    }
    assert "default:covalent:O-H" not in rules
    assert "default:hydrogen:O-H" not in rules

    rules.add(BondRule("Fe", "O", 2.5, 3.0, name="long:Fe-O"))
    assert rules["long:Fe-O"].min_distance == pytest.approx(2.5)
    rules.remove("long:Fe-O")
    assert "long:Fe-O" not in rules


def test_include_and_exclude_pairs_override_candidate_policy():
    included = get_default_bonds(
        Atoms("FeRh"),
        include_pairs={("Fe", "Rh")},
    )
    excluded = get_default_bonds(
        Atoms("FeO"),
        exclude_pairs={("Fe", "O")},
    )

    assert "default:Fe-Rh" in included
    assert "default:Fe-O" not in excluded


def test_default_oh_rules_preserve_half_open_boundary():
    covalent_max = get_default_bonds(Atoms("OH"))[
        "default:covalent:O-H"
    ].max_distance
    atoms = Atoms(
        "OH",
        positions=((0.0, 0.0, 0.0), (covalent_max, 0.0, 0.0)),
        cell=(10.0, 10.0, 10.0),
        pbc=False,
    )
    geometry = build_geometry(
        StructureModel(atoms),
        bond_rules=get_default_bonds(atoms),
    )

    assert len(geometry.bonds) == 1
    assert geometry.bonds[0].rule_id == "default:hydrogen:O-H"
