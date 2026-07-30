from pathlib import Path

import pytest

from atomic_povray import (
    AreaLight,
    Background,
    Camera,
    Color,
    RenderConfig,
    make_scene,
    scene_to_sdl,
)
from atomic_povray.backends.povray_sdl import _write_ini


def test_povray_overbright_rgb_is_allowed_but_alpha_remains_bounded():
    assert Color(1.05, 0.1, 0.05).red == pytest.approx(1.05)
    with pytest.raises(ValueError, match="Alpha"):
        Color(1.0, 1.0, 1.0, alpha=1.1)


def test_legacy_area_light_and_ambient_are_emitted():
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

    sdl = scene_to_sdl(scene)
    assert "ambient_light rgb <0.1, 0.1, 0.1>" in sdl
    assert "area_light" in sdl
    assert ", 9, 9" in sdl
    assert "adaptive 3" in sdl
    assert "color rgb <0.9, 0.9, 0.9>" in sdl


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
    ini = _write_ini(tmp_path / "scene.pov", tmp_path / "scene.png", config)

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
