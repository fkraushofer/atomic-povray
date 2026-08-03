"""Regression checks for the canonical shipped-default definitions."""

from __future__ import annotations

from inspect import signature

import pytest

from atomic_povray import (
    Camera,
    RenderConfig,
    StyleConfig,
    get_default_bonds,
    get_default_light,
    label_atoms,
    scene_to_sdl,
    write_scene,
)
from atomic_povray import _defaults as defaults


def test_geometry_and_style_defaults_come_from_canonical_values():
    assert signature(get_default_bonds).parameters["bond_scale"].default == (
        defaults.DEFAULT_BOND_SCALE
    )

    styles = StyleConfig()
    assert styles.preset_style == defaults.DEFAULT_PRESET_STYLE
    assert styles.atom_size_scale == pytest.approx(
        defaults.DEFAULT_PRESET_ATOM_SIZE_SCALES[defaults.DEFAULT_PRESET_STYLE]
    )
    assert styles.bond_size_scale == pytest.approx(
        defaults.DEFAULT_BOND_SIZE_SCALE
    )
    assert styles.default_bond.radius == pytest.approx(defaults.DEFAULT_BOND_RADIUS)
    assert styles.default_polyhedron.filter == pytest.approx(
        defaults.DEFAULT_POLYHEDRON_FILTER
    )
    assert styles.default_polyhedron.transmit == pytest.approx(
        defaults.DEFAULT_POLYHEDRON_TRANSMIT
    )
    assert styles.default_atom_finish == defaults.DEFAULT_ATOM_FINISH
    assert styles.default_bond_finish == defaults.DEFAULT_BOND_FINISH
    assert styles.default_polyhedron_finish == defaults.DEFAULT_POLYHEDRON_FINISH


def test_finish_defaults_are_listed_with_canonical_defaults():
    from atomic_povray import Color, Finish, Material

    values = (Finish(), Material(Color(1.0, 1.0, 1.0)))
    for value in values:
        assert value.ambient == pytest.approx(defaults.DEFAULT_FINISH_AMBIENT)
        assert value.diffuse == pytest.approx(defaults.DEFAULT_FINISH_DIFFUSE)
        assert value.phong == pytest.approx(defaults.DEFAULT_FINISH_PHONG)
        assert value.phong_size == pytest.approx(defaults.DEFAULT_FINISH_PHONG_SIZE)
        assert value.specular == pytest.approx(defaults.DEFAULT_FINISH_SPECULAR)
        assert value.emission == pytest.approx(defaults.DEFAULT_FINISH_EMISSION)


def test_camera_light_and_label_signatures_use_canonical_values():
    camera_fields = Camera.__dataclass_fields__
    assert camera_fields["up"].default == defaults.DEFAULT_CAMERA_UP
    assert camera_fields["angle"].default == defaults.DEFAULT_CAMERA_ANGLE
    assert camera_fields["width"].default == defaults.DEFAULT_CAMERA_WIDTH

    light_parameters = signature(get_default_light).parameters
    assert light_parameters["intensity"].default == defaults.DEFAULT_LIGHT_INTENSITY
    assert light_parameters["angular_diameter"].default == (
        defaults.DEFAULT_LIGHT_ANGULAR_DIAMETER
    )
    assert light_parameters["samples"].default == defaults.DEFAULT_LIGHT_SAMPLES
    assert light_parameters["adaptive"].default == defaults.DEFAULT_LIGHT_ADAPTIVE

    label_parameters = signature(label_atoms).parameters
    assert label_parameters["offset"].default == defaults.DEFAULT_LABEL_OFFSET
    assert label_parameters["size"].default == defaults.DEFAULT_LABEL_SIZE
    assert label_parameters["thickness"].default == defaults.DEFAULT_LABEL_THICKNESS
    assert label_parameters["font"].default == defaults.DEFAULT_LABEL_FONT
    assert label_parameters["color"].default == defaults.DEFAULT_LABEL_COLOR


def test_backend_defaults_come_from_canonical_values():
    config = RenderConfig()
    assert config.width == defaults.DEFAULT_RENDER_WIDTH
    assert config.height == defaults.DEFAULT_RENDER_HEIGHT
    assert config.quality == defaults.DEFAULT_RENDER_QUALITY
    assert config.antialias is defaults.DEFAULT_RENDER_ANTIALIAS
    assert config.transparent is defaults.DEFAULT_RENDER_TRANSPARENT
    assert config.display is defaults.DEFAULT_RENDER_DISPLAY
    assert config.executable == defaults.DEFAULT_POVRAY_EXECUTABLE
    assert config.povray_version == defaults.DEFAULT_POVRAY_VERSION

    assert signature(scene_to_sdl).parameters["aspect_ratio"].default == (
        defaults.DEFAULT_ASPECT_RATIO
    )
    write_parameters = signature(write_scene).parameters
    assert write_parameters["width"].default == defaults.DEFAULT_RENDER_WIDTH
    assert write_parameters["height"].default == defaults.DEFAULT_RENDER_HEIGHT
    assert write_parameters["povray_version"].default == (
        defaults.DEFAULT_POVRAY_VERSION
    )
