from __future__ import annotations

from ase import Atoms
import pytest

from atomic_povray import (
    AtomStyle,
    Background,
    BondRule,
    BondStyle,
    Camera,
    Color,
    CylinderPrimitive,
    Material,
    PointLight,
    SpherePrimitive,
    StructureModel,
    StyleConfig,
    apply_styles,
    build_geometry,
    make_scene,
    scene_to_sdl,
)


def simple_geometry():
    atoms = Atoms(
        "FeO",
        positions=((0.0, 0.0, 0.0), (1.8, 0.0, 0.0)),
        cell=(10.0, 10.0, 10.0),
        pbc=False,
    )
    return build_geometry(
        StructureModel(atoms),
        bond_rules=(BondRule("Fe", "O", 1.0, 2.0),),
    )


def test_default_bicolored_bond_becomes_two_half_cylinders():
    styled = apply_styles(
        simple_geometry(),
        StyleConfig(
            elements={
                "Fe": AtomStyle(0.6, Color(0.5, 0.1, 0.1)),
                "O": AtomStyle(0.4, Color(1.0, 0.8, 0.0)),
            },
            bonds={"Fe-O": BondStyle(radius=0.08)},
        ),
    )
    cylinders = [
        primitive
        for primitive in styled.primitives
        if isinstance(primitive, CylinderPrimitive)
    ]
    spheres = [
        primitive
        for primitive in styled.primitives
        if isinstance(primitive, SpherePrimitive)
    ]
    assert len(cylinders) == 2
    assert len(spheres) == 2
    assert cylinders[0].end == cylinders[1].start
    # The split makes the portions visible outside the 0.6/0.4 Å spheres equal.
    assert cylinders[0].end == pytest.approx((1.0, 0.0, 0.0))
    assert cylinders[0].material.color != cylinders[1].material.color


def test_single_color_bond_becomes_one_cylinder():
    styled = apply_styles(
        simple_geometry(),
        StyleConfig(
            bonds={
                "Fe-O": BondStyle(
                    radius=0.1,
                    color=Color(0.9, 0.9, 0.9),
                )
            }
        ),
    )
    cylinders = [
        primitive
        for primitive in styled.primitives
        if isinstance(primitive, CylinderPrimitive)
    ]
    assert len(cylinders) == 1


def test_extra_primitives_are_appended_and_written_to_sdl():
    styled = apply_styles(simple_geometry(), StyleConfig())
    extra = CylinderPrimitive(
        (0.0, 0.0, 0.0),
        (0.0, 0.0, 4.0),
        0.03,
        Material(Color(0.0, 0.0, 0.0)),
    )
    scene = make_scene(
        styled.primitives,
        camera=Camera.orthographic(
            location=(0.0, -20.0, 0.0),
            target=(0.0, 0.0, 0.0),
            up=(0.0, 0.0, 1.0),
            width=10.0,
        ),
        lights=(PointLight((5.0, -10.0, 10.0)),),
        background=Background(Color(1.0, 1.0, 1.0, alpha=0.0)),
        extra_primitives=(extra,),
    )
    sdl = scene_to_sdl(scene)

    assert scene.primitives[-1] is extra
    assert "orthographic" in sdl
    assert "light_source" in sdl
    assert "rgbf <1, 1, 1, 1>" in sdl
    assert sdl.count("cylinder {") == 3
    assert sdl.count("sphere {") == 2
