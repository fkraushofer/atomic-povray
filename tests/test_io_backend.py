from __future__ import annotations

from pathlib import Path

import pytest

from atomic_povray import (
    Background,
    Camera,
    Color,
    RenderConfig,
    make_scene,
    load_structure,
    write_scene,
)


def test_legacy_povin_is_explicitly_rejected():
    with pytest.raises(ValueError, match=r"\.povin"):
        load_structure("legacy.povin")


def test_write_empty_scene(tmp_path: Path):
    scene = make_scene(
        (),
        camera=Camera.perspective(
            location=(0.0, -10.0, 0.0),
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


@pytest.mark.parametrize("quality", (-1, 12))
def test_render_quality_is_validated(quality: int):
    with pytest.raises(ValueError, match="quality"):
        RenderConfig(quality=quality)

