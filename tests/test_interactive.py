from __future__ import annotations

from ase import Atoms
import pytest

from atomic_povray import (
    AreaLight,
    Background,
    Camera,
    Color,
    Control,
    DepthShading,
    PointLight,
    RenderConfig,
    StructureModel,
    StyleConfig,
    apply_interactive_values,
    apply_styles,
    available_controls,
    build_geometry,
    interactive_render,
    make_scene,
)
from atomic_povray.interactive import _LatestRenderController, _RenderJob
from atomic_povray.interactive._registry import (
    _get_control_spec,
    _symmetric_vector_length_range,
)


def _session(*, controls, depth_shading=None, geometry=True, lights=()):
    model = build_geometry(
        StructureModel(
            Atoms(
                "Fe",
                positions=((0.0, 0.0, 0.0),),
                cell=(10.0, 10.0, 10.0),
                pbc=False,
            )
        ),
        bond_rules=(),
    )
    styles = StyleConfig(depth_shading=depth_shading)
    styled = apply_styles(model, styles)
    camera = Camera.orthographic(
        direction=(0.0, 100.0, 0.0),
        target=(0.0, 0.0, 0.0),
        up=(0.0, 0.0, 1.0),
        width=20.0,
    )
    scene = make_scene(
        styled.primitives,
        camera=camera,
        lights=lights,
        background=Background(Color(1.0, 1.0, 1.0)),
    )
    session = interactive_render(
        scene,
        "interactive.png",
        RenderConfig(width=800, height=600),
        controls=controls,
        geometry=model if geometry else None,
        style_config=styles,
        show=False,
    )
    return session, scene, styles


def test_registry_contains_initial_camera_scene_style_and_depth_controls():
    names = set(available_controls())
    assert {
        "camera.direction",
        "camera.target",
        "camera.up",
        "scene.background.color",
        "scene.light.intensity",
        "scene.light.angular_diameter",
        "style.atom_size_scale",
        "style.default_atom_finish.phong",
        "style.depth_shading.enabled",
        "style.depth_shading.origin",
        "style.depth_shading.direction",
        "style.depth_shading.decay_length",
        "style.depth_shading.color",
    } <= names


@pytest.mark.parametrize(
    "field_name", ("location", "color", "intensity", "angular_diameter")
)
def test_indexed_light_controls_reuse_first_light_defaults(field_name):
    first = _get_control_spec(f"scene.light.{field_name}")
    indexed = _get_control_spec(f"scene.lights[2].{field_name}")

    assert indexed.kind == first.kind
    assert indexed.label == first.label
    assert indexed.limits == first.limits
    assert indexed.display_range == first.display_range
    assert indexed.step == first.step


def test_controls_accumulate_when_the_visible_set_changes():
    session, _, _ = _session(controls=["camera.direction"])
    session.set_value("camera.direction", (1.0, 2.0, 3.0), render=False)
    session.set_controls(
        [Control("style.atom_size_scale", min=0.1, max=2.0, step=0.01)],
        render=False,
    )
    session.set_value("style.atom_size_scale", 0.72, render=False)

    assert session.values == {
        "camera.direction": (1.0, 2.0, 3.0),
        "style.atom_size_scale": pytest.approx(0.72),
    }
    assert session.scene.camera.direction == (1.0, 2.0, 3.0)
    assert session.style_config.atom_size_scale == pytest.approx(0.72)


def test_returning_to_the_initial_value_removes_the_override():
    session, scene, _ = _session(controls=["camera.width"])
    session.set_value("camera.width", 30.0, render=False)
    assert session.values == {"camera.width": 30.0}
    session.set_value("camera.width", scene.camera.width, render=False)
    assert session.values == {}


def test_style_controls_require_geometry():
    with pytest.raises(ValueError, match="requires geometry and style_config"):
        _session(controls=["style.atom_size_scale"], geometry=False)


def test_depth_shading_values_survive_disable_and_reenable():
    initial = DepthShading(
        origin=(0.0, 0.0, 0.0),
        direction=(0.0, 0.0, 1.0),
        decay_length=5.0,
        target=Color(1.0, 1.0, 1.0),
    )
    session, _, _ = _session(
        controls=[
            "style.depth_shading.enabled",
            "style.depth_shading.origin",
            "style.depth_shading.decay_length",
        ],
        depth_shading=initial,
    )
    session.set_value("style.depth_shading.origin", (1.0, 2.0, 3.0), render=False)
    session.set_value("style.depth_shading.decay_length", 8.5, render=False)
    session.set_value("style.depth_shading.enabled", False, render=False)
    assert session.style_config.depth_shading is None

    session.set_value("style.depth_shading.enabled", True, render=False)
    assert session.style_config.depth_shading.origin == (1.0, 2.0, 3.0)
    assert session.style_config.depth_shading.decay_length == pytest.approx(8.5)


def test_depth_shading_field_automatically_includes_enabled_toggle():
    session, _, _ = _session(controls=["style.depth_shading.origin"])

    assert tuple(control.name for control in session.controls) == (
        "style.depth_shading.enabled",
        "style.depth_shading.origin",
    )
    session._ensure_ui()
    assert "style.depth_shading.enabled" in session._control_widgets
    origin_box = session._control_widgets["style.depth_shading.origin"]
    assert all(
        child.disabled for row in origin_box.children for child in row.children
    )

    session.set_value("style.depth_shading.enabled", True, render=False)
    assert all(
        not child.disabled for row in origin_box.children for child in row.children
    )


def test_explicit_depth_shading_toggle_is_not_duplicated():
    enabled = Control("style.depth_shading.enabled", label="Depth shading")
    session, _, _ = _session(controls=["style.depth_shading.origin", enabled])

    assert tuple(control.name for control in session.controls) == (
        "style.depth_shading.origin",
        "style.depth_shading.enabled",
    )
    assert session.controls[1] is enabled


def test_exported_values_reapply_the_complete_session_state():
    session, scene, styles = _session(
        controls=["camera.target", "style.depth_shading.enabled"]
    )
    session.set_value("camera.target", (3.0, 4.0, 5.0), render=False)
    session.set_value("style.depth_shading.origin", (1.0, 2.0, 3.0), render=False)
    session.set_value("style.depth_shading.decay_length", 7.0, render=False)
    session.set_value("style.depth_shading.enabled", True, render=False)

    reapplied_scene, reapplied_styles = apply_interactive_values(
        scene=scene,
        style_config=styles,
        values=session.values,
    )
    assert reapplied_scene.camera == session.scene.camera
    assert reapplied_scene.background == session.scene.background
    assert reapplied_styles == session.style_config
    source = session.as_python()
    assert "camera.target" in source
    assert "style.depth_shading.origin" in source
    assert "apply_interactive_values" in source


def test_default_preview_config_is_headless_and_keeps_aspect_ratio():
    session, _, _ = _session(controls=["camera.width"])
    assert session.preview_config.display is False
    assert session.preview_config.width == 480
    assert session.preview_config.height == 360
    assert session.preview_config.quality == 3
    assert session.preview_config.antialias is False


def test_preview_display_width_is_not_a_rendered_value():
    session, scene, _ = _session(controls=["camera.width"])
    session._ensure_ui()
    session.preview_width.value = 720
    assert session.values == {}
    assert session.scene.camera.width == scene.camera.width


def test_control_overrides_change_display_range_without_changing_limits():
    session, _, _ = _session(
        controls=[Control("camera.angle", min=-20.0, max=200.0)]
    )
    session._ensure_ui()
    slider, number = session._control_widgets["camera.angle"].children
    assert slider.min == number.min == pytest.approx(0.0)
    assert slider.max == number.max == pytest.approx(180.0)

    with pytest.raises(ValueError, match="must be at least 0.0"):
        session.set_value("camera.angle", -1.0, render=False)


def test_angle_control_includes_override_and_starts_disabled():
    session, _, _ = _session(controls=["camera.angle"])

    assert tuple(control.name for control in session.controls) == (
        "camera.angle_override",
        "camera.angle",
    )
    session._ensure_ui()
    angle = session._control_widgets["camera.angle"]
    assert all(child.disabled for child in angle.children)

    session.set_value("camera.angle_override", True, render=False)
    assert all(not child.disabled for child in angle.children)
    assert session.scene.camera.angle == pytest.approx(
        session.scene.camera.effective_angle
    )


def test_width_changes_automatic_perspective_angle_without_exporting_override():
    session, scene, _ = _session(controls=["camera.projection", "camera.width"])
    session.set_value("camera.projection", "perspective", render=False)
    session.set_value("camera.width", 30.0, render=False)

    assert session.scene.camera.angle is None
    assert session.scene.camera.effective_angle != pytest.approx(
        scene.camera.effective_angle
    )
    assert "camera.angle" not in session.values


def test_existing_value_expands_default_display_range_without_coercion():
    session, _, _ = _session(controls=["camera.width"])
    session.set_value("camera.width", 750.0, render=False)
    session._ensure_ui()
    slider, number = session._control_widgets["camera.width"].children
    assert slider.max == number.max == pytest.approx(750.0)
    assert slider.value == number.value == pytest.approx(750.0)


def test_vector_controls_share_symmetric_vector_length_display_range():
    session, _, _ = _session(controls=["camera.direction"])
    session._ensure_ui()
    vector_widget = session._control_widgets["camera.direction"]

    for slider, number in (row.children for row in vector_widget.children):
        assert slider.min == number.min == pytest.approx(-200.0)
        assert slider.max == number.max == pytest.approx(200.0)


def test_light_location_uses_twice_vector_length_display_range():
    session, _, _ = _session(
        controls=["scene.light.location"],
        lights=(PointLight((1.0, 2.0, 2.0)),),
    )
    session._ensure_ui()
    location = session.scene.lights[0].location
    expected = 2.0 * sum(component ** 2 for component in location) ** 0.5
    vector_widget = session._control_widgets["scene.light.location"]

    for slider, number in (row.children for row in vector_widget.children):
        assert slider.min == number.min == pytest.approx(-expected)
        assert slider.max == number.max == pytest.approx(expected)


def test_indexed_light_controls_update_lights_independently():
    lights = (
        PointLight((1.0, 2.0, 3.0)),
        PointLight((4.0, 5.0, 6.0)),
    )
    session, scene, styles = _session(
        controls=[
            "scene.lights[0].location",
            "scene.lights[1].location",
        ],
        lights=lights,
    )
    session._ensure_ui()
    assert set(session._control_widgets) == {
        "scene.lights[0].location",
        "scene.lights[1].location",
    }

    session.set_value(
        "scene.lights[0].location", (10.0, 20.0, 30.0), render=False
    )
    session.set_value(
        "scene.lights[1].location", (40.0, 50.0, 60.0), render=False
    )

    assert session.scene.lights[0].location == (10.0, 20.0, 30.0)
    assert session.scene.lights[1].location == (40.0, 50.0, 60.0)
    assert scene.lights == lights
    assert session.values == {
        "scene.lights[0].location": (10.0, 20.0, 30.0),
        "scene.lights[1].location": (40.0, 50.0, 60.0),
    }

    reapplied_scene, _ = apply_interactive_values(
        scene=scene,
        style_config=styles,
        values=session.values,
    )
    assert reapplied_scene.lights == session.scene.lights


def test_angular_diameter_controls_update_area_lights_independently():
    lights = (
        AreaLight((1.0, 2.0, 3.0), angular_diameter=5.0),
        AreaLight((4.0, 5.0, 6.0), angular_diameter=35.0),
    )
    session, scene, styles = _session(
        controls=[
            "scene.light.angular_diameter",
            "scene.lights[1].angular_diameter",
        ],
        lights=lights,
    )

    session.set_value(
        "scene.light.angular_diameter", 10.0, render=False
    )
    session.set_value(
        "scene.lights[1].angular_diameter", 45.0, render=False
    )

    assert session.scene.lights[0].angular_diameter == pytest.approx(10.0)
    assert session.scene.lights[1].angular_diameter == pytest.approx(45.0)
    assert session.values == {
        "scene.light.angular_diameter": 10.0,
        "scene.lights[1].angular_diameter": 45.0,
    }

    reapplied_scene, _ = apply_interactive_values(
        scene=scene,
        style_config=styles,
        values=session.values,
    )
    assert reapplied_scene.lights == session.scene.lights


def test_angular_diameter_control_requires_area_light():
    with pytest.raises(ValueError, match="not applicable"):
        _session(
            controls=["scene.light.angular_diameter"],
            lights=(PointLight((1.0, 2.0, 3.0)),),
        )


def test_indexed_light_control_rejects_missing_light():
    with pytest.raises(ValueError, match="not applicable"):
        _session(
            controls=["scene.lights[1].location"],
            lights=(PointLight((1.0, 2.0, 3.0)),),
        )


def test_symmetric_vector_length_range_has_minimum_extent_and_multiple():
    assert _symmetric_vector_length_range((0.0, 0.0, 0.0)) == (-2.0, 2.0)
    assert _symmetric_vector_length_range(
        (0.0, 0.0, 0.0), multiple=1.0
    ) == (-1.0, 1.0)
    assert _symmetric_vector_length_range(
        (1.0, 2.0, 2.0)
    ) == (-6.0, 6.0)

    with pytest.raises(ValueError, match="multiple must be positive"):
        _symmetric_vector_length_range((1.0, 0.0, 0.0), multiple=0.0)


def test_generic_widget_types_build_together():
    session, _, _ = _session(
        controls=[
            "camera.direction",
            "camera.projection",
            "scene.background.color",
            "style.draw_atoms",
            "style.depth_shading.decay_length",
        ]
    )
    session._ensure_ui()
    assert session.ui is not None
    assert len(session._links) == 4


def test_disabled_depth_shading_retains_but_disables_component_widgets():
    session, _, _ = _session(
        controls=[
            "style.depth_shading.enabled",
            "style.depth_shading.origin",
        ]
    )
    session._ensure_ui()
    origin_box = session._control_widgets["style.depth_shading.origin"]
    assert all(child.disabled for row in origin_box.children for child in row.children)

    session.set_value("style.depth_shading.enabled", True, render=False)
    assert all(
        not child.disabled for row in origin_box.children for child in row.children
    )


@pytest.mark.parametrize(
    ("executable", "expected"),
    [
        ("povray", ("povray", "preview.ini")),
        (
            "pvengine64.exe",
            (
                "pvengine64.exe",
                "/NR",
                "/RENDER",
                "preview.ini",
                "/EXIT",
            ),
        ),
    ],
)
def test_preview_process_command_and_png_capture(
    monkeypatch, tmp_path, executable, expected
):
    session, _, _ = _session(controls=["camera.width"])

    class FakePopen:
        returncode = 0

        def __init__(self, command, *, cwd, **kwargs):
            self.command = command
            self.cwd = cwd

        def communicate(self):
            ini = (self.cwd / "preview.ini").read_text(encoding="utf-8")
            output_line = next(
                line for line in ini.splitlines()
                if line.startswith("Output_File_Name=")
            )
            output = output_line.split("=", 1)[1]
            from pathlib import Path

            Path(output).write_bytes(b"fake png")
            return b"stdout", b""

    monkeypatch.setattr("atomic_povray.interactive.subprocess.Popen", FakePopen)
    controller = _LatestRenderController(
        output=tmp_path / "full.png",
        on_result=lambda result: None,
        on_status=lambda message: None,
        debounce_s=0.1,
        max_wait_s=0.3,
    )
    config = RenderConfig(
        width=320,
        height=240,
        quality=3,
        display=False,
        executable=executable,
    )
    result = controller._render_sync(
        _RenderJob(1, session.scene, config, False)
    )
    assert result.png == b"fake png"
    assert result.render_result.command == expected
