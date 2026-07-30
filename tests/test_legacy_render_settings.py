from pathlib import Path

import pytest

from atomic_povray import (
    AreaLight,
    AtomStyle,
    Background,
    BondStyle,
    Camera,
    Color,
    Finish,
    Material,
    RenderConfig,
    StyleConfig,
    make_scene,
    scene_to_sdl,
    write_ini,
)


def test_povray_overbright_rgb_is_allowed_but_alpha_remains_bounded():
    assert Color(1.05, 0.1, 0.05).red == pytest.approx(1.05)
    with pytest.raises(ValueError, match="Alpha"):
        Color(1.0, 1.0, 1.0, alpha=1.1)


def test_legacy_area_light_gamma_and_ambient_are_emitted():
    camera = Camera.orthographic(
        location=(5.0, -100.0, 25.5),
        target=(5.0, 0.0, 25.5),
        up=(0.0, 0.0, 1.0),
    )
    light = AreaLight(
        location=(-4000.0, -6000.0, 6000.0),
        target=camera.target,
        intensity=0.9,
        angular_diameter=35.0,
        samples=(9, 9),
        adaptive=3,
    )
    scene = make_scene(
        (),
        camera=camera,
        lights=(light,),
        ambient_light=Color(0.1, 0.1, 0.1),
        background=Background(Color(1.0, 1.0, 1.0, alpha=0.0)),
    )

    sdl = scene_to_sdl(scene, povray_version="3.8")
    assert sdl.startswith("#version 3.8;")
    assert "assumed_gamma 1.0" in sdl
    assert "ambient_light rgb <0.1, 0.1, 0.1>" in sdl
    assert "area_light" in sdl
    assert ", 9, 9" in sdl
    assert "adaptive 3" in sdl
    assert "color rgb <0.9, 0.9, 0.9>" in sdl


def test_default_finish_is_shared_and_specific_styles_can_override_it():
    default_finish = Finish()
    atom_finish = Finish(
        ambient=0.10,
        diffuse=0.60,
        phong=0.30,
        phong_size=10,
    )
    styles = StyleConfig(default_finish=default_finish)
    color = Color(1.05, 0.10, 0.05)

    default_atom_material = AtomStyle(0.4, color).resolved_material(
        styles.default_finish
    )
    default_bond_material = BondStyle().material_for(
        color,
        styles.default_finish,
    )
    overridden_atom_material = AtomStyle(
        0.4,
        color,
        finish=atom_finish,
    ).resolved_material(styles.default_finish)

    assert default_atom_material == default_finish.material(color)
    assert default_bond_material == default_finish.material(color)
    assert default_finish == Finish(
        ambient=0.10,
        diffuse=0.60,
        phong=0.0,
        phong_size=10,
    )
    assert overridden_atom_material == atom_finish.material(color)

    explicit_material = Material(color, phong=0.8)
    assert (
        BondStyle(material=explicit_material).material_for(
            color,
            styles.default_finish,
        )
        is explicit_material
    )


def test_legacy_ini_render_controls(tmp_path: Path):
    config = RenderConfig(
        width=1024,
        height=768,
        quality=5,
        antialias_threshold=0.05,
        sampling_method=2,
        display_gamma=2.0,
        file_gamma=2.0,
        transparent=True,
        display=True,
    )
    ini = write_ini(tmp_path / "scene.pov", tmp_path / "scene.png", config)

    values = ini.read_text(encoding="utf-8")
    assert "Width=1024" in values
    assert "Height=768" in values
    assert "Quality=5" in values
    assert "Display=On" in values
    assert "Antialias_Threshold=0.05" in values
    assert "Sampling_Method=2" in values
    assert "Display_Gamma=2.0" in values
    assert "File_Gamma=2.0" in values
    assert "Output_File_Type=N" in values
    assert "Output_Alpha=On" in values


def test_povray_version_is_configurable_and_validated():
    camera = Camera.perspective(
        location=(0, -10, 0),
        target=(0, 0, 0),
        up=(0, 0, 1),
    )
    scene = make_scene((), camera=camera)

    assert scene_to_sdl(scene).startswith("#version 3.8;")
    assert scene_to_sdl(scene, povray_version="3.7").startswith("#version 3.7;")
    with pytest.raises(ValueError, match="povray_version"):
        RenderConfig(povray_version="3.8-beta")
