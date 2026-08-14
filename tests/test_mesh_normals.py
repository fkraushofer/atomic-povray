"""Tests for optional triangle-mesh vertex normals."""

import pytest

from atomic_povray import (
    Camera,
    Color,
    Material,
    TriangleMeshPrimitive,
    make_scene,
    scene_to_sdl,
)


VERTICES = (
    (0.0, 0.0, 0.0),
    (1.0, 0.0, 0.0),
    (0.0, 1.0, 0.0),
)
FACES = ((0, 1, 2),)
NORMALS = (
    (0.0, 0.0, 1.0),
    (0.0, 0.0, 1.0),
    (0.0, 0.0, 1.0),
)
MATERIAL = Material(Color(1.0, 0.0, 0.0))


def _mesh_sdl(mesh: TriangleMeshPrimitive) -> str:
    scene = make_scene(
        (mesh,),
        camera=Camera.orthographic(
            direction=(0.0, 0.0, -10.0),
            target=(0.0, 0.0, 0.0),
        ),
    )
    return scene_to_sdl(scene)


def test_triangle_mesh_normals_must_match_vertex_count():
    with pytest.raises(ValueError, match="match the vertex count"):
        TriangleMeshPrimitive(
            vertices=VERTICES,
            faces=FACES,
            material=MATERIAL,
            normals=NORMALS[:1],
        )


def test_povray_mesh2_writes_vertex_normals_and_indices():
    sdl = _mesh_sdl(
        TriangleMeshPrimitive(
            vertices=VERTICES,
            faces=FACES,
            material=MATERIAL,
            normals=NORMALS,
        )
    )

    assert "normal_vectors { 3," in sdl
    assert sdl.count("<0, 0, 1>,") == 3
    assert "normal_indices { 1," in sdl
    assert "<0, 1, 2>," in sdl


def test_povray_mesh2_without_normals_is_unchanged():
    sdl = _mesh_sdl(
        TriangleMeshPrimitive(
            vertices=VERTICES,
            faces=FACES,
            material=MATERIAL,
        )
    )

    assert "normal_vectors" not in sdl
    assert "normal_indices" not in sdl
    assert "double_illuminate" not in sdl


def test_povray_mesh2_writes_two_sided_lighting_modifier():
    sdl = _mesh_sdl(
        TriangleMeshPrimitive(
            vertices=VERTICES,
            faces=FACES,
            material=MATERIAL,
            two_sided_lighting=True,
        )
    )

    assert "  double_illuminate\n}" in sdl
