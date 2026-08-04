"""Immutable interactive state and cumulative override replay."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isclose
from typing import Any

from ..scene import Fog, Scene
from ..styling import DepthShading, StyleConfig

@dataclass(frozen=True)
class _InteractiveState:
    scene: Scene
    style_config: StyleConfig | None
    depth_shading: DepthShading
    fog: Fog


def _initial_state(scene: Scene, styles: StyleConfig | None) -> _InteractiveState:
    shading = (
        styles.depth_shading
        if styles is not None and styles.depth_shading is not None
        else DepthShading(
            origin=scene.camera.target,
            direction=scene.camera.direction,
            decay_length=max(1.0, scene.camera.width / 2),
            target=scene.background.color,
        )
    )
    fog = scene.fog or Fog(
        distance=max(1.0, scene.camera.width * 2),
        color=scene.background.color,
    )
    return _InteractiveState(scene, styles, shading, fog)


def _values_equal(left: Any, right: Any) -> bool:
    if isinstance(left, float) and isinstance(right, float):
        return isclose(left, right, rel_tol=0.0, abs_tol=1e-12)
    return left == right


def apply_interactive_values(
    *,
    scene: Scene,
    style_config: StyleConfig | None,
    values: Mapping[str, Any],
) -> tuple[Scene, StyleConfig | None]:
    """Apply exported interactive overrides to fresh scene/style objects."""

    from ._registry import _CONTROL_SPECS

    state = _initial_state(scene, style_config)
    for name, value in values.items():
        try:
            spec = _CONTROL_SPECS[name]
        except KeyError:
            raise ValueError(f"unknown interactive control {name!r}") from None
        if not spec.applicable(state):
            raise ValueError(f"control {name!r} is not applicable to this state")
        state = spec.setter(state, spec.coerce(value))
    return state.scene, state.style_config



__all__ = ["apply_interactive_values"]
