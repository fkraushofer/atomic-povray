from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from atomic_povray import (
    Background,
    Camera,
    Color,
    Fog,
    Material,
    Radiosity,
    RenderConfig,
    SpherePrimitive,
    make_scene,
    load_structure,
    render_scene,
    scene_to_sdl,
    write_ini,
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


@pytest.mark.parametrize("max_trace_level", (0, -1))
def test_max_trace_level_must_be_positive(max_trace_level: int):
    with pytest.raises(ValueError, match="max_trace_level"):
        RenderConfig(max_trace_level=max_trace_level)


def test_max_trace_level_and_additional_pov_are_written_to_sdl():
    scene = make_scene(
        (),
        camera=Camera.perspective(
            direction=(0.0, 10.0, 0.0),
            target=(0.0, 0.0, 0.0),
            up=(0.0, 0.0, 1.0),
        ),
    )

    text = scene_to_sdl(
        scene,
        max_trace_level=20,
        additional_pov="#declare Custom_Value = 3;\n",
    )

    assert "  max_trace_level 20\n}" in text
    assert "}\n\n#declare Custom_Value = 3;\n\ncamera {" in text



def test_radiosity_preset_is_written_inside_global_settings():
    scene = make_scene(
        (
            SpherePrimitive(
                center=(0.0, 0.0, 0.0),
                radius=1.0,
                material=Material(Color(1.0, 0.0, 0.0), ambient=0.0),
            ),
        ),
        camera=Camera.perspective(
            direction=(0.0, 10.0, 0.0),
            target=(0.0, 0.0, 0.0),
            up=(0.0, 0.0, 1.0),
        ),
    )

    text = scene_to_sdl(scene, radiosity=Radiosity())

    assert """  radiosity {
    pretrace_start 0.08
    pretrace_end 0.01
    count 100
    error_bound 0.5
    recursion_limit 2
  }
}""" in text


def test_radiosity_warns_for_nonzero_material_ambient_but_writes_scene():
    scene = make_scene(
        (
            SpherePrimitive(
                center=(0.0, 0.0, 0.0),
                radius=1.0,
                material=Material(Color(1.0, 0.0, 0.0)),
            ),
        ),
        camera=Camera.perspective(
            direction=(0.0, 10.0, 0.0),
            target=(0.0, 0.0, 0.0),
            up=(0.0, 0.0, 1.0),
        ),
    )

    with pytest.warns(UserWarning, match=r"ambient != 0"):
        text = scene_to_sdl(scene, radiosity=Radiosity())

    assert "radiosity {" in text
    assert "sphere {" in text


@pytest.mark.parametrize(
    ("kwargs", "message"),
    (
        ({"pretrace_end": 0.09, "pretrace_start": 0.08}, "pretrace_end"),
        ({"count": 0}, "count"),
        ({"error_bound": 0.0}, "error_bound"),
        ({"recursion_limit": 21}, "recursion_limit"),
    ),
)
def test_radiosity_parameters_are_validated(kwargs, message):
    with pytest.raises((TypeError, ValueError), match=message):
        Radiosity(**kwargs)


def test_additional_ini_is_appended(tmp_path: Path):
    ini = write_ini(
        tmp_path / "scene.pov",
        tmp_path / "scene.png",
        RenderConfig(additional_ini="Max_Image_Buffer_Memory=1024\n"),
    )

    assert ini.read_text(encoding="utf-8").endswith(
        "Output_Alpha=Off\nMax_Image_Buffer_Memory=1024\n"
    )


def test_constant_fog_is_written_to_sdl():
    scene = make_scene(
        (),
        camera=Camera.perspective(
            direction=(0.0, 10.0, 0.0),
            target=(0.0, 0.0, 0.0),
            up=(0.0, 0.0, 1.0),
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


def test_render_warns_when_quality_disables_fog(tmp_path: Path, monkeypatch):
    scene = make_scene(
        (),
        camera=Camera.perspective(
            direction=(0.0, 10.0, 0.0),
            target=(0.0, 0.0, 0.0),
            up=(0.0, 0.0, 1.0),
        ),
        fog=Fog(distance=25.0),
    )
    monkeypatch.setattr(
        "atomic_povray.backends.povray_sdl.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(stdout="", stderr=""),
    )

    with pytest.warns(UserWarning, match="fog requires quality 9 or higher"):
        render_scene(
            scene,
            tmp_path / "fog.png",
            RenderConfig(quality=3),
        )


def test_render_runs_in_output_directory_and_can_clean_up(
    tmp_path: Path, monkeypatch
):
    scene = make_scene(
        (),
        camera=Camera.perspective(
            direction=(0.0, 10.0, 0.0),
            target=(0.0, 0.0, 0.0),
            up=(0.0, 0.0, 1.0),
        ),
    )
    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return SimpleNamespace(stdout="done", stderr="")

    monkeypatch.setattr(
        "atomic_povray.backends.povray_sdl.subprocess.run",
        fake_run,
    )
    output = tmp_path / "output" / "scene.png"

    result = render_scene(
        scene,
        output,
        RenderConfig(executable="pvengine64.exe"),
        cleanup=True,
    )

    command, kwargs = calls[0]
    assert command == ("pvengine64.exe", "/RENDER", "scene.ini", "/EXIT")
    assert kwargs["cwd"] == output.parent.resolve()
    assert result.image_path == output
    assert not result.scene_path.exists()
    assert not result.ini_path.exists()


def test_render_keeps_intermediate_files_after_failure(tmp_path: Path, monkeypatch):
    scene = make_scene(
        (),
        camera=Camera.perspective(
            direction=(0.0, 10.0, 0.0),
            target=(0.0, 0.0, 0.0),
            up=(0.0, 0.0, 1.0),
        ),
    )

    def fail(*args, **kwargs):
        raise RuntimeError("render failed")

    monkeypatch.setattr(
        "atomic_povray.backends.povray_sdl.subprocess.run",
        fail,
    )
    output = tmp_path / "output" / "scene.png"

    with pytest.raises(RuntimeError, match="render failed"):
        render_scene(scene, output, RenderConfig(), cleanup=True)

    assert output.with_suffix(".pov").exists()
    assert output.with_suffix(".ini").exists()


@pytest.mark.parametrize("distance", (0.0, -1.0, float("inf"), float("nan")))
def test_fog_distance_is_positive_and_finite(distance):
    with pytest.raises(ValueError, match="fog distance"):
        Fog(distance=distance)
