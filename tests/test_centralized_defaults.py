"""Regression checks for the canonical shipped-default definitions."""

from __future__ import annotations

import pytest

from atomic_povray import (
    Camera,
    DEFAULT_PROFILE,
    RenderConfig,
    StyleConfig,
    get_default_bonds,
)
from atomic_povray import _defaults as defaults


def test_geometry_and_style_defaults_come_from_canonical_values():
    assert DEFAULT_PROFILE.geometry.bond_scale == defaults.DEFAULT_BOND_SCALE

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


def test_camera_light_and_label_profiles_use_canonical_values():
    camera_fields = Camera.__dataclass_fields__
    assert camera_fields["up"].default == defaults.DEFAULT_CAMERA_UP
    assert camera_fields["angle"].default is None
    assert camera_fields["width"].default == defaults.DEFAULT_CAMERA_WIDTH

    scene = DEFAULT_PROFILE.scene
    assert scene.light_intensity == defaults.DEFAULT_LIGHT_INTENSITY
    assert scene.light_angular_diameter == defaults.DEFAULT_LIGHT_ANGULAR_DIAMETER
    assert scene.light_samples == defaults.DEFAULT_LIGHT_SAMPLES
    assert scene.light_adaptive == defaults.DEFAULT_LIGHT_ADAPTIVE

    labels = DEFAULT_PROFILE.labels
    assert labels.offset == defaults.DEFAULT_LABEL_OFFSET
    assert labels.size == defaults.DEFAULT_LABEL_SIZE
    assert labels.thickness == defaults.DEFAULT_LABEL_THICKNESS
    assert labels.font == defaults.DEFAULT_LABEL_FONT
    assert labels.color == defaults.DEFAULT_LABEL_COLOR


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

    assert config.width / config.height == pytest.approx(defaults.DEFAULT_ASPECT_RATIO)
