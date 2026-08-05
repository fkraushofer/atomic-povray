"""Interactive rendering session and public constructor."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import replace
from html import escape
from pathlib import Path
from typing import Any

from ..backends.povray_sdl import RenderConfig
from ..model import GeometryModel
from ..primitives import Primitive
from ..scene import Scene
from ..styling import StyleConfig, apply_styles
from ._control import Control
from ._registry import _CONTROL_SPECS
from ._rendering import InteractiveRenderResult, _LatestRenderController
from ._state import _initial_state, _values_equal
from ._widgets import _WidgetMixin


_DEPTH_SHADING_PREFIX = "style.depth_shading."
_DEPTH_SHADING_ENABLED = f"{_DEPTH_SHADING_PREFIX}enabled"


def _include_depth_shading_toggle(controls: list[Control]) -> list[Control]:
    """Add the enabled toggle before the first depth-shading field."""

    if any(control.name == _DEPTH_SHADING_ENABLED for control in controls):
        return controls
    for index, control in enumerate(controls):
        if control.name.startswith(_DEPTH_SHADING_PREFIX):
            return [
                *controls[:index],
                Control(_DEPTH_SHADING_ENABLED),
                *controls[index:],
            ]
    return controls


class InteractiveRenderSession(_WidgetMixin):
    """State and notebook UI for a curated set of scene/style controls."""

    def __init__(
        self,
        scene: Scene,
        output: str | Path,
        render_config: RenderConfig,
        *,
        controls: Iterable[str | Control],
        geometry: GeometryModel | None,
        style_config: StyleConfig | None,
        extra_primitives: tuple[Primitive, ...],
        preview_config: RenderConfig,
        debounce_s: float,
        max_wait_s: float,
        display_width: int,
        build_ui: bool,
    ) -> None:
        self.output = Path(output)
        self.render_config = render_config
        self.preview_config = preview_config
        self.geometry = geometry
        self.extra_primitives = extra_primitives
        self._base_state = _initial_state(scene, style_config)
        self._state = self._base_state
        self._controls: tuple[Control, ...] = ()
        self.last_preview_result: InteractiveRenderResult | None = None
        self.last_full_result: InteractiveRenderResult | None = None
        self.last_error: str | None = None
        self._widgets: Any = None
        self._links: list[Any] = []
        self._control_widgets: dict[str, Any] = {}
        self.ui: Any = None
        self.image: Any = None
        self.status: Any = None
        self._controls_box: Any = None
        self._display_width = display_width
        self._controller = _LatestRenderController(
            output=self.output,
            on_result=self._publish,
            on_status=self._set_status,
            debounce_s=debounce_s,
            max_wait_s=max_wait_s,
        )
        self.set_controls(controls, render=False)
        if build_ui:
            self._ensure_ui()

    @property
    def controls(self) -> tuple[Control, ...]:
        return self._controls

    @property
    def scene(self) -> Scene:
        return self._build_scene()

    @property
    def style_config(self) -> StyleConfig | None:
        return self._state.style_config

    @property
    def values(self) -> dict[str, Any]:
        values: dict[str, Any] = {}
        for name, spec in _CONTROL_SPECS.items():
            if not spec.applicable(self._base_state):
                continue
            base = spec.getter(self._base_state)
            current = spec.getter(self._state)
            if not _values_equal(base, current):
                values[name] = current
        return values

    def _build_scene(self) -> Scene:
        scene = self._state.scene
        if self._state.style_config is None:
            return scene
        if self.geometry is None:
            return scene
        styled = apply_styles(self.geometry, self._state.style_config)
        return replace(
            scene,
            primitives=(*styled.primitives, *self.extra_primitives),
        )

    def set_value(self, name: str, value: Any, *, render: bool = True) -> None:
        """Set one registered value; useful for programmatic refinement/tests."""

        try:
            spec = _CONTROL_SPECS[name]
        except KeyError:
            raise ValueError(f"unknown interactive control {name!r}") from None
        if not spec.applicable(self._state):
            raise ValueError(f"control {name!r} is not applicable to this session")
        if name.startswith("style.") and self.geometry is None:
            raise ValueError("style controls require geometry")
        self._state = spec.setter(self._state, spec.coerce(value))
        if self.ui is not None:
            self._refresh_conditional_controls()
        if render and self.ui is not None:
            self._request_preview()

    def set_controls(
        self,
        controls: Iterable[str | Control],
        *,
        render: bool = True,
    ) -> None:
        """Replace visible controls without discarding accumulated changes."""

        requested: list[Control] = []
        for value in controls:
            control = Control(value) if isinstance(value, str) else value
            if not isinstance(control, Control):
                raise TypeError("controls must contain strings or Control objects")
            requested.append(control)

        resolved: list[Control] = []
        for control in _include_depth_shading_toggle(requested):
            try:
                spec = _CONTROL_SPECS[control.name]
            except KeyError:
                raise ValueError(
                    f"unknown interactive control {control.name!r}; "
                    "use available_controls() to inspect supported names"
                ) from None
            if not spec.applicable(self._state):
                raise ValueError(
                    f"control {control.name!r} is not applicable to this session"
                )
            if control.name.startswith("style.") and self.geometry is None:
                raise ValueError(
                    f"control {control.name!r} requires geometry and style_config"
                )
            if control.step is not None and control.step <= 0:
                raise ValueError(f"{control.name} step must be positive")
            if control.min is not None and control.max is not None:
                if control.min >= control.max:
                    raise ValueError(
                        f"{control.name} min must be smaller than max"
                    )
            resolved.append(control)
        self._controls = tuple(resolved)
        if self.ui is not None:
            self._rebuild_controls_ui()
            if render:
                self._request_preview()

    def as_python(self) -> str:
        """Return cumulative overrides as copyable Python source."""

        lines = [
            "from atomic_povray import Color, apply_interactive_values",
            "",
            "INTERACTIVE_VALUES = {",
        ]
        for name, value in self.values.items():
            lines.append(f"    {name!r}: {value!r},")
        lines.extend(
            [
                "}",
                "scene, style_config = apply_interactive_values(",
                "    scene=scene,",
                "    style_config=style_config,",
                "    values=INTERACTIVE_VALUES,",
                ")",
            ]
        )
        return "\n".join(lines) + "\n"



    def _request_preview(self, *, immediate: bool = False) -> None:
        self._controller.request(
            self._build_scene(),
            self.preview_config,
            immediate=immediate,
        )

    def render_full(self) -> int:
        """Queue a full-quality render using the original RenderConfig."""

        return self._controller.request(
            self._build_scene(),
            self.render_config,
            full_quality=True,
            immediate=True,
        )

    async def cancel(self) -> None:
        await self._controller.cancel()

    def _publish(self, result: InteractiveRenderResult) -> None:
        if result.timings.full_quality:
            self.last_full_result = result
        else:
            self.last_preview_result = result
        if self.image is not None:
            self.image.value = result.png

    def _set_status(self, message: str) -> None:
        self.last_error = self._controller.last_error
        if self.status is None:
            return
        lower = message.lower()
        if "failed" in lower:
            color = "#b42318"
        elif any(word in lower for word in ("rendering", "queued", "pending", "stale")):
            color = "#b54708"
        elif "cancel" in lower:
            color = "#667085"
        else:
            color = "#027a48"
        self.status.value = (
            f'<span style="color:{color}">●</span> {escape(message)}'
        )

    def display(self) -> None:
        """Display the session UI and immediately queue its first preview."""

        self._ensure_ui()
        from IPython.display import display

        display(self.ui)
        self._request_preview(immediate=True)



def interactive_render(
    scene: Scene,
    output: str | Path,
    render_config: RenderConfig | None = None,
    *,
    controls: Iterable[str | Control],
    geometry: GeometryModel | None = None,
    style_config: StyleConfig | None = None,
    extra_primitives: tuple[Primitive, ...] = (),
    preview_config: RenderConfig | None = None,
    debounce_s: float = 0.12,
    max_wait_s: float = 0.30,
    display_width: int = 480,
    show: bool = True,
) -> InteractiveRenderSession:
    """Create a notebook session for selected scene/style variables.

    Scene and camera controls need only ``scene``. Style controls additionally
    require the original ``geometry`` and ``style_config`` so styling can be
    reapplied without rebuilding geometry.
    """

    render_config = render_config or RenderConfig()
    if preview_config is None:
        preview_width = min(480, render_config.width)
        preview_height = max(
            1, round(preview_width * render_config.height / render_config.width)
        )
        preview_config = replace(
            render_config,
            width=preview_width,
            height=preview_height,
            quality=min(3, render_config.quality),
            antialias=False,
            display=False,
            radiosity=None,
        )
    elif preview_config.display:
        preview_config = replace(preview_config, display=False)
    session = InteractiveRenderSession(
        scene,
        output,
        render_config,
        controls=controls,
        geometry=geometry,
        style_config=style_config,
        extra_primitives=extra_primitives,
        preview_config=preview_config,
        debounce_s=debounce_s,
        max_wait_s=max_wait_s,
        display_width=display_width,
        build_ui=show,
    )
    if show:
        session.display()
    return session
