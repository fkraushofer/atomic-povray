from __future__ import annotations

from pathlib import Path

import pytest

from atomic_povray import (
    Background,
    Camera,
    Color,
    Fog,
    RenderConfig,
    make_scene,
    load_structure,
    scene_to_sdl,
    write_scene,
)


def test_legacy_povin_is_explicitly_rejected():
    with pytest.raises(ValueError, match=r"\.povin"):
        load_structure("legacy.povin")


def test_write_empty_scene(tmp_path: Path):
    scene = make_scene(
        (),
        camera=Camera.perspective(
            direction=(0.0, 10.0, 0.0),
            target=(0.0, 0.0, 0.0),
            up=(0.0, 0.0, 1.0),
        ),
        background=Background(Color(1.0, 1.0, 1.0)),
    )
    output = write_scene(scene, tmp_path / "scene.pov", width=1600, height=900)
    text = output.read_text(encoding="utf-8")
    assert output.exists()
    assert "angle 35" in text
    assert "camera {" in text
    assert "location <0, -10, 0>" in text
    assert "look_at <0, 0, 0>" in text


def test_camera_location_follows_target_with_fixed_direction():
    camera = Camera.orthographic(
        direction=(0.0, 20.0, 5.0),
        target=(3.0, 4.0, 5.0),
    )

    assert camera.location == pytest.approx((3.0, -16.0, 0.0))

    moved = Camera.orthographic(
        direction=camera.direction,
        target=(8.0, 9.0, 10.0),
    )
    assert moved.location == pytest.approx((8.0, -11.0, 5.0))


@pytest.mark.parametrize("quality", (-1, 12))
def test_render_quality_is_validated(quality: int):
    with pytest.raises(ValueError, match="quality"):
        RenderConfig(quality=quality)



def test_constant_fog_is_written_to_sdl():
    scene = make_scene(
        (),
        camera=Camera.perspective(
            direction=(0.0, 10.0, 0.0),
            target=(0.0, 0.0, 0.0),
        ),
        fog=Fog(
            distance=25.0,
            color=Color(0.9, 0.8, 0.7),
        ),
    )

    text = scene_to_sdl(scene)

    assert "fog {" in text
    assert "fog_type 1" in text
    assert "distance 25" in text
    assert "color rgbf <0.9, 0.8, 0.7, 0>" in text


@pytest.mark.parametrize("distance", (0.0, -1.0, float("inf"), float("nan")))
def test_fog_distance_is_positive_and_finite(distance):
    with pytest.raises(ValueError, match="fog distance"):
        Fog(distance=distance)
