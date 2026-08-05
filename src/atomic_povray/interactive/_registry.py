"""Catalogue of supported controls and their presentation defaults.

This is the central place to browse or adjust labels, groups, hard limits,
display ranges, and steps for variables exposed by interactive rendering.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from functools import partial
import re
from typing import Any

import numpy as np

from ..primitives import Color
from ..scene import AreaLight, Background, PointLight, Scene
from ..styling import StyleConfig
from ._control import ControlKind
from ._state import _InteractiveState


Getter = Callable[[_InteractiveState], Any]
Setter = Callable[[_InteractiveState, Any], _InteractiveState]
Applicability = Callable[[_InteractiveState], bool]
DisplayRange = tuple[float, float] | Callable[[Any], tuple[float, float]]


def _symmetric_vector_length_range(
    vector: Any,
    *,
    multiple: float = 2.0,
) -> tuple[float, float]:
    """Return shared symmetric component bounds based on a vector's length."""

    if multiple <= 0.0:
        raise ValueError("vector display-range multiple must be positive")
    length = float(np.linalg.norm(vector))
    extent = max(length, 1.0) * multiple
    return (-extent, extent)


@dataclass(frozen=True)
class _ControlSpec:
    name: str
    kind: ControlKind
    label: str
    group: str
    getter: Getter
    setter: Setter
    limits: tuple[float | None, float | None] = (None, None)
    display_range: DisplayRange | None = None
    step: float | None = None
    choices: tuple[Any, ...] = ()
    applicable: Applicability = lambda state: True

    def coerce(self, value: Any) -> Any:
        if self.kind == "boolean":
            if not isinstance(value, bool):
                raise TypeError(f"{self.name} must be a bool")
            return value
        if self.kind == "choice":
            if value not in self.choices:
                raise ValueError(
                    f"{self.name} must be one of {self.choices!r}, got {value!r}"
                )
            return value
        if self.kind == "color":
            if isinstance(value, str):
                value = Color.from_hex(value)
            if not isinstance(value, Color):
                raise TypeError(f"{self.name} must be a Color or hex string")
            return value
        if self.kind == "vector":
            try:
                vector = tuple(float(component) for component in value)
            except (TypeError, ValueError) as error:
                raise TypeError(f"{self.name} must be a three-vector") from error
            if len(vector) != 3:
                raise ValueError(f"{self.name} must contain exactly three values")
            for component in vector:
                self._validate_limits(component)
            return vector
        if isinstance(value, bool):
            raise TypeError(f"{self.name} must be a number")
        number = float(value)
        self._validate_limits(number)
        return number

    def _validate_limits(self, number: float) -> None:
        minimum, maximum = self.limits
        if minimum is not None and number < minimum:
            raise ValueError(f"{self.name} must be at least {minimum}")
        if maximum is not None and number > maximum:
            raise ValueError(f"{self.name} must be at most {maximum}")


def _with_scene(state: _InteractiveState, scene: Scene) -> _InteractiveState:
    return replace(state, scene=scene)


def _camera_spec(
    name: str,
    kind: ControlKind,
    label: str,
    *,
    limits: tuple[float | None, float | None] = (None, None),
    display_range: DisplayRange | None = None,
    step: float | None = None,
    choices: tuple[Any, ...] = (),
) -> _ControlSpec:
    field_name = name.rsplit(".", 1)[1]

    def getter(state: _InteractiveState) -> Any:
        return getattr(state.scene.camera, field_name)

    def setter(state: _InteractiveState, value: Any) -> _InteractiveState:
        camera = replace(state.scene.camera, **{field_name: value})
        return _with_scene(state, replace(state.scene, camera=camera))

    return _ControlSpec(
        name, kind, label, "Camera", getter, setter,
        limits, display_range, step, choices,
    )


def _camera_angle_specs() -> tuple[_ControlSpec, _ControlSpec]:
    """Return the explicit-angle toggle and its numeric value control."""

    def override_getter(state: _InteractiveState) -> bool:
        return state.scene.camera.angle is not None

    def override_setter(
        state: _InteractiveState, value: bool
    ) -> _InteractiveState:
        camera = state.scene.camera
        angle = camera.effective_angle if value else None
        return _with_scene(
            state, replace(state.scene, camera=replace(camera, angle=angle))
        )

    def angle_getter(state: _InteractiveState) -> float:
        return state.scene.camera.effective_angle

    def angle_setter(
        state: _InteractiveState, value: float
    ) -> _InteractiveState:
        camera = replace(state.scene.camera, angle=value)
        return _with_scene(state, replace(state.scene, camera=camera))

    return (
        _ControlSpec(
            "camera.angle_override", "boolean", "Override angle", "Camera",
            override_getter, override_setter,
        ),
        _ControlSpec(
            "camera.angle", "number", "Perspective angle", "Camera",
            angle_getter, angle_setter,
            limits=(0.0, 180.0), display_range=(1.0, 179.0), step=0.5,
        ),
    )


def _scene_attribute_spec(
    name: str,
    kind: ControlKind,
    label: str,
    group: str,
    *,
    limits: tuple[float | None, float | None] = (None, None),
    display_range: DisplayRange | None = None,
    step: float | None = None,
) -> _ControlSpec:
    field_name = name.rsplit(".", 1)[1]

    def getter(state: _InteractiveState) -> Any:
        return getattr(state.scene, field_name)

    def setter(state: _InteractiveState, value: Any) -> _InteractiveState:
        return _with_scene(state, replace(state.scene, **{field_name: value}))

    return _ControlSpec(
        name, kind, label, group, getter, setter,
        limits, display_range, step,
    )


def _style_attribute_spec(
    name: str,
    kind: ControlKind,
    label: str,
    *,
    limits: tuple[float | None, float | None] = (None, None),
    display_range: DisplayRange | None = None,
    step: float | None = None,
    choices: tuple[Any, ...] = (),
) -> _ControlSpec:
    field_name = name.rsplit(".", 1)[1]

    def getter(state: _InteractiveState) -> Any:
        assert state.style_config is not None
        return getattr(state.style_config, field_name)

    def setter(state: _InteractiveState, value: Any) -> _InteractiveState:
        assert state.style_config is not None
        return replace(
            state,
            style_config=replace(state.style_config, **{field_name: value}),
        )

    return _ControlSpec(
        name, kind, label, "Appearance", getter, setter,
        limits, display_range, step, choices,
        applicable=lambda state: state.style_config is not None,
    )


def _style_color_spec(
    name: str,
    label: str,
    style_field: str,
) -> _ControlSpec:
    def getter(state: _InteractiveState) -> Color:
        assert state.style_config is not None
        color = getattr(state.style_config, style_field).color
        if color is None:
            raise ValueError(f"{name} has no resolved color")
        return color

    def setter(state: _InteractiveState, value: Color) -> _InteractiveState:
        assert state.style_config is not None
        current = getattr(state.style_config, style_field)
        return replace(
            state,
            style_config=replace(
                state.style_config,
                **{style_field: replace(current, color=value)},
            ),
        )

    return _ControlSpec(
        name, "color", label, "Appearance", getter, setter,
        applicable=lambda state: (
            state.style_config is not None
            and getattr(state.style_config, style_field).color is not None
        ),
    )


def _finish_spec(name: str, label: str, finish_field: str) -> _ControlSpec:
    def getter(state: _InteractiveState) -> float:
        assert state.style_config is not None
        finish = getattr(state.style_config, finish_field)
        return float(getattr(finish, name.rsplit(".", 1)[1]))

    def setter(state: _InteractiveState, value: float) -> _InteractiveState:
        assert state.style_config is not None
        finish = getattr(state.style_config, finish_field)
        finish = replace(finish, **{name.rsplit(".", 1)[1]: value})
        return replace(
            state,
            style_config=replace(state.style_config, **{finish_field: finish}),
        )

    return _ControlSpec(
        name, "number", label, "Appearance", getter, setter,
        limits=(0.0, 1.0), display_range=(0.0, 1.0), step=0.05,
        applicable=lambda state: state.style_config is not None,
    )


def _depth_spec(
    name: str,
    kind: ControlKind,
    label: str,
    field_name: str,
    *,
    limits: tuple[float | None, float | None] = (None, None),
    display_range: DisplayRange | None = None,
    step: float | None = None,
) -> _ControlSpec:
    def getter(state: _InteractiveState) -> Any:
        return getattr(state.depth_shading, field_name)

    def setter(state: _InteractiveState, value: Any) -> _InteractiveState:
        shading = replace(state.depth_shading, **{field_name: value})
        styles = state.style_config
        assert styles is not None
        if styles.depth_shading is not None:
            styles = replace(styles, depth_shading=shading)
        return replace(state, depth_shading=shading, style_config=styles)

    return _ControlSpec(
        name, kind, label, "Depth shading", getter, setter,
        limits, display_range, step,
        applicable=lambda state: state.style_config is not None,
    )


def _light_at(
    state: _InteractiveState,
    index: int,
) -> PointLight | AreaLight:
    try:
        return state.scene.lights[index]
    except IndexError:
        raise ValueError(f"the scene has no light at index {index}") from None


def _light_spec(
    name: str,
    kind: ControlKind,
    label: str,
    field_name: str,
    *,
    index: int = 0,
    group: str = "Lighting",
    limits: tuple[float | None, float | None] = (None, None),
    display_range: DisplayRange | None = None,
    step: float | None = None,
) -> _ControlSpec:
    def getter(state: _InteractiveState) -> Any:
        return getattr(_light_at(state, index), field_name)

    def setter(state: _InteractiveState, value: Any) -> _InteractiveState:
        lights = list(state.scene.lights)
        lights[index] = replace(_light_at(state, index), **{field_name: value})
        return _with_scene(state, replace(state.scene, lights=tuple(lights)))

    def applicable(state: _InteractiveState) -> bool:
        if index >= len(state.scene.lights):
            return False
        return hasattr(state.scene.lights[index], field_name)

    return _ControlSpec(
        name, kind, label, group, getter, setter,
        limits, display_range, step,
        applicable=applicable,
    )


_INDEXED_LIGHT_CONTROL = re.compile(
    r"scene\.lights\[(?P<index>\d+)\]\."
    r"(?P<field>location|color|intensity|angular_diameter)\Z"
)


def _indexed_light_spec(
    name: str,
    control_specs: dict[str, _ControlSpec],
) -> _ControlSpec | None:
    """Build a control spec for ``scene.lights[index].field`` names."""

    match = _INDEXED_LIGHT_CONTROL.fullmatch(name)
    if match is None:
        return None
    index = int(match.group("index"))
    field_name = match.group("field")
    template = control_specs[f"scene.light.{field_name}"]
    return _light_spec(
        name,
        template.kind,
        template.label,
        field_name,
        index=index,
        group=f"Light {index + 1}",
        limits=template.limits,
        display_range=template.display_range,
        step=template.step,
    )


def _make_control_specs() -> dict[str, _ControlSpec]:
    angle_override, angle = _camera_angle_specs()
    specs = [
        _camera_spec(
            "camera.direction", "vector", "Direction",
            display_range=_symmetric_vector_length_range, step=0.1,
        ),
        _camera_spec(
            "camera.target", "vector", "Target",
            display_range=_symmetric_vector_length_range, step=0.1,
        ),
        _camera_spec(
            "camera.up", "vector", "Up",
            display_range=_symmetric_vector_length_range, step=0.1,
        ),
        _camera_spec(
            "camera.projection", "choice", "Projection",
            choices=("orthographic", "perspective"),
        ),
        angle_override,
        angle,
        _camera_spec(
            "camera.width", "number", "Width",
            limits=(0.0, None), display_range=(1.0, 100.0), step=0.25,
        ),
        _scene_attribute_spec(
            "scene.ambient_light", "color", "Ambient light", "Scene"
        ),
        _light_spec(
            "scene.light.location", "vector", "Location", "location",
            display_range=_symmetric_vector_length_range, step=0.1,
        ),
        _light_spec("scene.light.color", "color", "Color", "color"),
        _light_spec(
            "scene.light.intensity", "number", "Intensity", "intensity",
            limits=(0.0, None), display_range=(0.0, 10.0), step=0.05,
        ),
        _light_spec(
            "scene.light.angular_diameter", "number", "Angular diameter",
            "angular_diameter", limits=(0.0, 180.0),
            display_range=(1.0, 90.0), step=0.5,
        ),
        _style_attribute_spec(
            "style.preset_style", "choice", "Preset",
            choices=("ball_and_stick", "space_filling", "polyhedral"),
        ),
        _style_attribute_spec(
            "style.atom_size_scale", "number", "Atom size scale",
            limits=(0.0, None), display_range=(0.05, 2.0), step=0.05,
        ),
        _style_attribute_spec(
            "style.bond_size_scale", "number", "Bond size scale",
            limits=(0.0, None), display_range=(0.05, 5.0), step=0.05,
        ),
        _style_attribute_spec("style.draw_atoms", "boolean", "Draw atoms"),
        _style_attribute_spec("style.draw_bonds", "boolean", "Draw bonds"),
        _style_attribute_spec(
            "style.draw_polyhedra", "boolean", "Draw polyhedra"
        ),
        _style_color_spec(
            "style.default_atom.color", "Default atom color", "default_atom"
        ),
        _style_color_spec(
            "style.default_bond.color", "Default bond color", "default_bond"
        ),
        _style_color_spec(
            "style.default_polyhedron.color",
            "Default polyhedron color",
            "default_polyhedron",
        ),
        _finish_spec(
            "style.default_atom_finish.phong", "Atom phong", "default_atom_finish"
        ),
        _finish_spec(
            "style.default_bond_finish.phong", "Bond phong", "default_bond_finish"
        ),
        _finish_spec(
            "style.default_polyhedron_finish.phong",
            "Polyhedron phong",
            "default_polyhedron_finish",
        ),
        _depth_spec(
            "style.depth_shading.origin", "vector", "Origin", "origin",
            display_range=_symmetric_vector_length_range, step=0.1,
        ),
        _depth_spec(
            "style.depth_shading.direction",
            "vector",
            "Direction",
            "direction",
            display_range=_symmetric_vector_length_range,
            step=0.1,
        ),
        _depth_spec(
            "style.depth_shading.decay_length",
            "number",
            "Decay length",
            "decay_length",
            limits=(0.001, None),
            display_range=(0.1, 50.0),
            step=0.1,
        ),
        _depth_spec(
            "style.depth_shading.color", "color", "Target color", "target"
        ),
        _depth_spec(
            "style.depth_shading.shade_alpha",
            "boolean",
            "Shade transparency",
            "shade_alpha",
        ),
    ]

    def background_getter(state: _InteractiveState) -> Color:
        return state.scene.background.color

    def background_setter(
        state: _InteractiveState, value: Color
    ) -> _InteractiveState:
        return _with_scene(
            state, replace(state.scene, background=Background(value))
        )

    specs.append(
        _ControlSpec(
            "scene.background.color",
            "color",
            "Background",
            "Scene",
            background_getter,
            background_setter,
        )
    )

    def fog_enabled_getter(state: _InteractiveState) -> bool:
        return state.scene.fog is not None

    def fog_enabled_setter(
        state: _InteractiveState, value: bool
    ) -> _InteractiveState:
        fog = state.fog if value else None
        return _with_scene(state, replace(state.scene, fog=fog))

    specs.append(
        _ControlSpec(
            "scene.fog.enabled",
            "boolean",
            "Enabled",
            "Fog",
            fog_enabled_getter,
            fog_enabled_setter,
        )
    )
    for field_name, kind, label, limits, display_range, step in (
        (
            "distance", "number", "Distance",
            (0.0, None), (0.01, 1000.0), 0.5,
        ),
        ("color", "color", "Color", (None, None), None, None),
    ):
        def fog_getter(
            state: _InteractiveState, field_name: str = field_name
        ) -> Any:
            return getattr(state.fog, field_name)

        def fog_setter(
            state: _InteractiveState,
            value: Any,
            field_name: str = field_name,
        ) -> _InteractiveState:
            fog = replace(state.fog, **{field_name: value})
            scene = state.scene
            if scene.fog is not None:
                scene = replace(scene, fog=fog)
            return replace(state, scene=scene, fog=fog)

        specs.append(
            _ControlSpec(
                f"scene.fog.{field_name}",
                kind,
                label,
                "Fog",
                fog_getter,
                fog_setter,
                limits,
                display_range,
                step,
            )
        )

    def depth_enabled_getter(state: _InteractiveState) -> bool:
        return bool(
            state.style_config is not None
            and state.style_config.depth_shading is not None
        )

    def depth_enabled_setter(
        state: _InteractiveState, value: bool
    ) -> _InteractiveState:
        assert state.style_config is not None
        return replace(
            state,
            style_config=replace(
                state.style_config,
                depth_shading=state.depth_shading if value else None,
            ),
        )

    specs.append(
        _ControlSpec(
            "style.depth_shading.enabled",
            "boolean",
            "Enabled",
            "Depth shading",
            depth_enabled_getter,
            depth_enabled_setter,
            applicable=lambda state: state.style_config is not None,
        )
    )
    return {spec.name: spec for spec in specs}


_CONTROL_SPECS = _make_control_specs()


def _get_control_spec(name: str) -> _ControlSpec:
    """Resolve a registered name or an indexed light-control name."""

    spec = _CONTROL_SPECS.get(name)
    if spec is None:
        spec = _indexed_light_spec(name, _CONTROL_SPECS)
    if spec is None:
        raise ValueError(f"unknown interactive control {name!r}")
    return spec


def available_controls() -> tuple[str, ...]:
    """Return the static names accepted by :func:`interactive_render`.

    Lights may additionally use dynamic ``scene.lights[index].field`` names.
    """

    return tuple(_CONTROL_SPECS)
