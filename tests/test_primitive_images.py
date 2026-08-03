from __future__ import annotations

import numpy as np
import pytest
from ase import Atoms

from atomic_povray import (
    Color,
    CylinderPrimitive,
    Material,
    SpherePrimitive,
    StructureModel,
    TextPrimitive,
    TriangleMeshPrimitive,
    primitive_images,
)


MATERIAL = Material(Color(1.0, 1.0, 1.0))


def structure() -> StructureModel:
    return StructureModel(
        Atoms("H", positions=((0.0, 0.0, 0.0),), cell=((2, 0, 0), (1, 3, 0), (0, 0, 4)))
    )


@pytest.mark.parametrize(
    ("primitive", "point_name", "expected"),
    (
        (SpherePrimitive((0, 0, 0), 1, MATERIAL), "center", (3, 3, 0)),
        (CylinderPrimitive((0, 0, 0), (1, 0, 0), 1, MATERIAL), "start", (3, 3, 0)),
        (
            TextPrimitive("x", (0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), MATERIAL),
            "position",
            (3, 3, 0),
        ),
    ),
)
def test_primitive_images_translates_point_primitives(primitive, point_name, expected):
    images = primitive_images(primitive, structure(), ((1, 2), (1, 2), (0, 1)))

    assert len(images) == 1
    assert getattr(images[0], point_name) == pytest.approx(expected)


def test_primitive_images_translates_mesh_geometry_but_not_normals():
    mesh = TriangleMeshPrimitive(
        vertices=((0, 0, 0), (1, 0, 0), (0, 1, 0)),
        faces=((0, 1, 2),),
        material=MATERIAL,
        normals=((0, 0, 1),) * 3,
        reference_position=(0.25, 0.25, 0),
    )

    image = primitive_images(mesh, structure(), ((-1, 0), (0, 1), (1, 2)))[0]

    assert image.vertices[0] == pytest.approx((-2, 0, 4))
    assert image.reference_position == pytest.approx((-1.75, 0.25, 4))
    assert image.faces is mesh.faces
    assert image.normals is mesh.normals
    assert image.material is mesh.material


def test_primitive_images_uses_half_open_ranges_in_deterministic_order():
    primitive = SpherePrimitive((0, 0, 0), 1, MATERIAL)

    images = primitive_images(primitive, structure(), ((-1, 2), (0, 1), (0, 1)))

    assert [image.center for image in images] == pytest.approx(
        [(-2, 0, 0), (0, 0, 0), (2, 0, 0)]
    )


@pytest.mark.parametrize(
    "ranges",
    (
        ((0.0, 1.0), (0, 1), (0, 1)),
        ((0, 1), (0, 1), (False, 1)),
    ),
)
def test_primitive_images_rejects_non_integer_ranges(ranges):
    with pytest.raises(TypeError, match="integers"):
        primitive_images(SpherePrimitive((0, 0, 0), 1, MATERIAL), structure(), ranges)
