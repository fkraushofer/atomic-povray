"""Tests for reusable user profiles and their override precedence."""

from dataclasses import FrozenInstanceError, replace

import pytest
from ase import Atoms

from atomic_povray import (
    DEFAULT_PROFILE,
    AtomStyle,
    Background,
    Camera,
    Color,
    ElementOverride,
    RenderConfig,
    StyleConfig,
    get_default_bonds,
    get_default_light,
    make_scene,
)
from atomic_povray.defaults import default_atom_color, default_atom_radius


def test_profiles_are_immutable_and_replacement_is_independent():
    custom = replace(
        DEFAULT_PROFILE,
        render=replace(DEFAULT_PROFILE.render, quality=3),
    )

    assert DEFAULT_PROFILE.render.quality == 5
    assert custom.render.quality == 3
    with pytest.raises(FrozenInstanceError):
        custom.render.quality = 7
    with pytest.raises(TypeError):
        custom.style.element_overrides["Fe"] = ElementOverride(radius=0.7)


def test_geometry_profile_changes_bond_and_hydrogen_cutoffs():
    profile = replace(
        DEFAULT_PROFILE,
        geometry=replace(
            DEFAULT_PROFILE.geometry,
            bond_scale=1.1,
            hydrogen_bond_max=2.4,
        ),
    )
    rules = get_default_bonds(Atoms("OH"), profile=profile, print_table=False)

    covalent = rules["default:covalent:O-H"]
    hydrogen = rules["default:hydrogen:O-H"]
    assert covalent.max_distance == pytest.approx(
        1.1 * (default_atom_radius("O") + default_atom_radius("H"))
    )
    assert hydrogen.max_distance == pytest.approx(2.4)

    explicit = get_default_bonds(
        Atoms("OH"), profile=profile, bond_scale=1.05, print_table=False
    )
    assert explicit["default:covalent:O-H"].max_distance == pytest.approx(
        1.05 * (default_atom_radius("O") + default_atom_radius("H"))
    )


def test_element_overrides_fall_back_field_by_field_and_scene_wins():
    custom_color = Color(0.1, 0.2, 0.9)
    profile = replace(
        DEFAULT_PROFILE,
        style=replace(
            DEFAULT_PROFILE.style,
            element_overrides={"Fe": ElementOverride(color=custom_color)},
        ),
    )

    profiled = StyleConfig(profile=profile).atom_style("Fe")
    assert profiled.color == custom_color
    assert profiled.radius == pytest.approx(default_atom_radius("Fe"))

    scene_override = StyleConfig(
        profile=profile,
        elements={"Fe": AtomStyle(radius=0.7)},
    ).atom_style("Fe")
    assert scene_override.radius == pytest.approx(0.7)
    assert scene_override.color == custom_color

    oxygen = StyleConfig(profile=profile).atom_style("O")
    assert oxygen.color == default_atom_color("O")
    assert oxygen.radius == pytest.approx(default_atom_radius("O"))


def test_style_profile_controls_presets_finishes_and_hydrogen_bonds():
    profile = replace(
        DEFAULT_PROFILE,
        style=replace(
            DEFAULT_PROFILE.style,
            atom_size_scale=0.55,
            bond_radius=0.12,
            hydrogen_bond_radius=0.07,
            hydrogen_bond_segments=6,
        ),
    )
    styles = StyleConfig(profile=profile)

    assert styles.atom_size_scale == pytest.approx(0.55)
    assert styles.default_bond.radius == pytest.approx(0.12)
    hydrogen = styles.bond_style("default:hydrogen:O-H")
    assert hydrogen.radius == pytest.approx(0.07)
    assert hydrogen.segments == 6

    explicit = StyleConfig(
        profile=profile,
        atom_size_scale=0.3,
        default_bond=replace(styles.default_bond, radius=0.2),
    )
    assert explicit.atom_size_scale == pytest.approx(0.3)
    assert explicit.default_bond.radius == pytest.approx(0.2)


def test_style_profile_has_independent_default_atom_size_scale():
    profile = replace(
        DEFAULT_PROFILE,
        style=replace(DEFAULT_PROFILE.style, atom_size_scale=0.7),
    )

    assert StyleConfig(profile=profile).atom_size_scale == pytest.approx(0.7)
    assert StyleConfig(
        profile=profile, preset_style="space_filling"
    ).atom_size_scale == pytest.approx(1.0)


def test_scene_and_render_profile_defaults_with_explicit_precedence():
    profile = replace(
        DEFAULT_PROFILE,
        scene=replace(
            DEFAULT_PROFILE.scene,
            camera_direction=(0.0, 10.0, 0.0),
            camera_up=(0.0, 0.0, 1.0),
            camera_width=31.0,
            light_intensity=2.5,
            background_color=Color(0.2, 0.3, 0.4),
            ambient_light=Color(0.6, 0.6, 0.6),
        ),
        render=replace(
            DEFAULT_PROFILE.render,
            width=1200,
            height=900,
            quality=3,
            antialias_threshold=0.05,
            sampling_method=2,
            display_gamma=2.0,
            file_gamma=2.0,
        ),
    )
    camera = Camera.orthographic(
        target=(0.0, 0.0, 0.0),
        profile=profile,
    )
    light = get_default_light(camera, profile=profile)
    scene = make_scene((), camera=camera, profile=profile)
    render = RenderConfig(profile=profile)

    assert camera.width == pytest.approx(31.0)
    assert camera.direction == (0.0, 10.0, 0.0)
    assert light.intensity == pytest.approx(2.5)
    assert scene.background == Background(Color(0.2, 0.3, 0.4))
    assert scene.ambient_light == Color(0.6, 0.6, 0.6)
    assert (render.width, render.height, render.quality) == (1200, 900, 3)
    assert render.antialias_threshold == pytest.approx(0.05)
    assert render.sampling_method == 2
    assert render.display_gamma == pytest.approx(2.0)
    assert render.file_gamma == pytest.approx(2.0)

    explicit_camera = Camera.orthographic(
        direction=(0.0, 0.0, 10.0),
        target=(0.0, 0.0, 0.0),
        width=12.0,
        profile=profile,
    )
    explicit_scene = make_scene(
        (), camera=camera, ambient_light=1.25, profile=profile
    )
    explicit_render = RenderConfig(profile=profile, quality=7)
    assert explicit_camera.width == pytest.approx(12.0)
    assert explicit_scene.ambient_light == Color(1.25, 1.25, 1.25)
    assert explicit_render.quality == 7
