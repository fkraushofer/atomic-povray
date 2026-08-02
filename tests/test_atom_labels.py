"""Tests for renderer-independent atom labels and POV-Ray text output."""

import pytest
from ase import Atoms

from atomic_povray import (
    AtomInstance, AtomKey, AtomStyle, Camera, Color, GeometryModel, Material,
    StructureModel, StyledGeometry, TextPrimitive, label_atoms, make_scene,
    scene_to_sdl,
)


def _styled_geometry() -> StyledGeometry:
    atoms = Atoms("FeO", positions=((1.0, 2.0, 3.0), (4.0, 5.0, 6.0)))
    instances = (
        AtomInstance(AtomKey(0), "Fe", (0.0, 0.0, 0.0), (1.0, 2.0, 3.0)),
        AtomInstance(AtomKey(1), "O", (0.0, 0.0, 0.0), (4.0, 5.0, 6.0)),
    )
    geometry = GeometryModel(StructureModel(atoms), instances, (), ((), ()))
    return StyledGeometry(
        geometry,
        (),
        {
            AtomKey(0): AtomStyle(radius=0.5, color=Color(1.0, 0.0, 0.0)),
            AtomKey(1): AtomStyle(radius=0.25, color=Color(0.0, 0.0, 1.0)),
        },
    )


def _camera() -> Camera:
    return Camera.orthographic(
        direction=(0.0, 0.0, -10.0),
        target=(0.0, 0.0, 0.0),
        up=(0.0, 1.0, 0.0),
    )


def test_label_atoms_uses_surface_radius_and_camera_relative_offset():
    labels = label_atoms(
        _styled_geometry(), camera=_camera(), offset=(0.2, 0.3, 0.4)
    )
    assert labels[0].text == "Fe1"
    assert labels[0].position == pytest.approx((1.2, 2.3, 3.9))
    assert labels[0].right == pytest.approx((1.0, 0.0, 0.0))
    assert labels[0].up == pytest.approx((0.0, 1.0, 0.0))
    assert labels[0].normal == pytest.approx((0.0, 0.0, 1.0))


def test_label_atoms_supports_selection_and_custom_text():
    labels = label_atoms(
        _styled_geometry(),
        camera=_camera(),
        selection=lambda atom: atom.symbol == "O",
        labels=lambda atom: f'"{atom.symbol}\\n{atom.key.source_index}"',
    )
    assert len(labels) == 1
    assert labels[0].text == '"O\\n1"'


def test_povray_text_serialization_escapes_strings_and_writes_transform():
    primitive = TextPrimitive(
        text='O "top"\\line\n2',
        position=(1.0, 2.0, 3.0),
        right=(1.0, 0.0, 0.0),
        up=(0.0, 1.0, 0.0),
        normal=(0.0, 0.0, 1.0),
        material=Material(Color(0.0, 0.0, 0.0)),
        font='my"font.ttf',
        size=0.5,
        thickness=0.03,
    )
    sdl = scene_to_sdl(make_scene((primitive,), camera=_camera()))
    assert 'text { ttf "my\\"font.ttf"' in sdl
    assert '"O \\"top\\"\\\\line\\n2"' in sdl
    assert "0.03, 0" in sdl
    assert "scale 0.5" in sdl
    assert "matrix <1, 0, 0, 0, 1, 0, 0, 0, 1, 1, 2, 3>" in sdl


@pytest.mark.parametrize("argument", ({"size": 0.0}, {"thickness": -0.1}, {"font": ""}))
def test_label_atoms_validates_text_geometry(argument):
    with pytest.raises((ValueError, TypeError)):
        label_atoms(_styled_geometry(), camera=_camera(), **argument)
