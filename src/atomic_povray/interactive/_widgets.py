"""Notebook widget construction and presentation for interactive sessions."""

from __future__ import annotations

import asyncio
from typing import Any

from ..primitives import Color
from ._control import Control
from ._registry import _CONTROL_SPECS, _ControlSpec

class _WidgetMixin:
    def _ensure_ui(self) -> None:
        if self.ui is not None:
            return
        try:
            import ipywidgets as widgets
        except ImportError as error:
            raise ImportError(
                "interactive_render requires ipywidgets; install notebook support "
                "with `python -m pip install 'atomic-povray[notebook]'`."
            ) from error
        self._widgets = widgets
        self._controls_box = widgets.VBox()
        self.full_button = widgets.Button(
            description="Render full quality", button_style="primary"
        )
        self.cancel_button = widgets.Button(description="Cancel")
        self.preview_width = widgets.BoundedIntText(
            description="Preview px",
            min=200,
            max=1600,
            step=40,
            value=self._display_width,
            layout=widgets.Layout(width="190px"),
        )
        self.status = widgets.HTML(value="idle")
        self.image = widgets.Image(
            format="png",
            layout=widgets.Layout(
                width=f"{self._display_width}px",
                height="auto",
                object_fit="contain",
            ),
        )
        self.ui = widgets.VBox(
            [
                self._controls_box,
                widgets.HBox(
                    [self.full_button, self.cancel_button, self.preview_width]
                ),
                self.status,
                self.image,
            ]
        )
        self.full_button.on_click(lambda button: self.render_full())
        self.cancel_button.on_click(
            lambda button: asyncio.create_task(self.cancel())
        )
        self.preview_width.observe(self._preview_width_changed, names="value")
        self._rebuild_controls_ui()

    def _rebuild_controls_ui(self) -> None:
        widgets = self._widgets
        self._links.clear()
        self._control_widgets.clear()
        grouped: dict[str, list[Any]] = {}
        for control in self._controls:
            spec = _CONTROL_SPECS[control.name]
            widget = self._make_widget(control, spec)
            self._control_widgets[control.name] = widget
            grouped.setdefault(spec.group, []).append(widget)
        sections = [widgets.VBox(children) for children in grouped.values()]
        accordion = widgets.Accordion(children=sections)
        for index, title in enumerate(grouped):
            accordion.set_title(index, title)
        if sections:
            accordion.selected_index = 0
        self._controls_box.children = (accordion,)
        self._refresh_conditional_controls()

    def _refresh_conditional_controls(self) -> None:
        depth_enabled = bool(
            self._state.style_config is not None
            and self._state.style_config.depth_shading is not None
        )
        fog_enabled = self._state.scene.fog is not None
        angle_overridden = self._state.scene.camera.angle is not None
        for name, widget in self._control_widgets.items():
            if name.startswith("style.depth_shading.") and not name.endswith(
                ".enabled"
            ):
                self._set_widget_disabled(widget, not depth_enabled)
            elif name.startswith("scene.fog.") and not name.endswith(".enabled"):
                self._set_widget_disabled(widget, not fog_enabled)
            elif name == "camera.angle":
                self._set_widget_disabled(widget, not angle_overridden)

    def _set_widget_disabled(self, widget: Any, disabled: bool) -> None:
        children = getattr(widget, "children", ())
        if children:
            for child in children:
                self._set_widget_disabled(child, disabled)
        elif hasattr(widget, "disabled"):
            widget.disabled = disabled

    def _bounds(
        self,
        control: Control,
        spec: _ControlSpec,
        current: float,
        display_range: tuple[float, float] | None = None,
    ) -> tuple[float, float, float]:
        step = control.step if control.step is not None else spec.step or 0.1
        default_span = max(10.0 * step, abs(current) * 2.0, 1.0)
        display_minimum, display_maximum = (
            display_range
            if display_range is not None
            else (current - default_span, current + default_span)
        )
        minimum = (
            control.min
            if control.min is not None
            else display_minimum
        )
        maximum = (
            control.max
            if control.max is not None
            else display_maximum
        )
        limit_minimum, limit_maximum = spec.limits
        if limit_minimum is not None:
            minimum = max(float(minimum), limit_minimum)
        if limit_maximum is not None:
            maximum = min(float(maximum), limit_maximum)
        minimum = min(float(minimum), current)
        maximum = max(float(maximum), current)
        if minimum == maximum:
            maximum = minimum + step
        return minimum, maximum, step

    def _make_widget(self, control: Control, spec: _ControlSpec) -> Any:
        widgets = self._widgets
        value = spec.getter(self._state)
        label = control.label or spec.label
        if spec.kind == "boolean":
            widget = widgets.Checkbox(description=label, value=value)
            widget.observe(
                lambda change, name=spec.name: self.set_value(name, change["new"]),
                names="value",
            )
            return widget
        if spec.kind == "choice":
            widget = widgets.Dropdown(
                description=label, options=spec.choices, value=value
            )
            widget.observe(
                lambda change, name=spec.name: self.set_value(name, change["new"]),
                names="value",
            )
            return widget
        if spec.kind == "color":
            widget = widgets.ColorPicker(
                description=label,
                value=_color_to_hex(value),
                concise=False,
            )
            widget.observe(
                lambda change, name=spec.name: self._set_color(name, change["new"]),
                names="value",
            )
            return widget
        if spec.kind == "vector":
            rows = []
            display_range = (
                spec.display_range(value)
                if callable(spec.display_range)
                else spec.display_range
            )
            for index, (component, axis) in enumerate(zip(value, "xyz")):
                minimum, maximum, step = self._bounds(
                    control, spec, float(component), display_range
                )
                slider = widgets.FloatSlider(
                    description=f"{label} {axis}",
                    min=minimum,
                    max=maximum,
                    step=step,
                    value=component,
                    continuous_update=True,
                    layout=widgets.Layout(width="430px"),
                )
                number = widgets.BoundedFloatText(
                    min=minimum,
                    max=maximum,
                    step=step,
                    value=component,
                    layout=widgets.Layout(width="95px"),
                )
                self._links.append(
                    widgets.link((slider, "value"), (number, "value"))
                )
                number.observe(
                    lambda change, name=spec.name, index=index: (
                        self._set_vector_component(name, index, change["new"])
                    ),
                    names="value",
                )
                rows.append(widgets.HBox([slider, number]))
            return widgets.VBox(rows)
        display_range = (
            spec.display_range(value)
            if callable(spec.display_range)
            else spec.display_range
        )
        minimum, maximum, step = self._bounds(
            control, spec, float(value), display_range
        )
        slider = widgets.FloatSlider(
            description=label,
            min=minimum,
            max=maximum,
            step=step,
            value=value,
            continuous_update=True,
            layout=widgets.Layout(width="430px"),
        )
        number = widgets.BoundedFloatText(
            min=minimum,
            max=maximum,
            step=step,
            value=value,
            layout=widgets.Layout(width="95px"),
        )
        self._links.append(widgets.link((slider, "value"), (number, "value")))
        number.observe(
            lambda change, name=spec.name: self.set_value(name, change["new"]),
            names="value",
        )
        return widgets.HBox([slider, number])

    def _set_vector_component(
        self, name: str, index: int, value: float
    ) -> None:
        vector = list(_CONTROL_SPECS[name].getter(self._state))
        vector[index] = value
        self.set_value(name, tuple(vector))

    def _set_color(self, name: str, value: str) -> None:
        current = _CONTROL_SPECS[name].getter(self._state)
        rgb = Color.from_hex(value)
        self.set_value(
            name,
            Color(
                rgb.red,
                rgb.green,
                rgb.blue,
                filter=current.filter,
                transmit=current.transmit,
            ),
        )

    def _preview_width_changed(self, change: dict[str, Any]) -> None:
        self.image.layout.width = f"{change['new']}px"


def _color_to_hex(color: Color) -> str:
    channels = (color.red, color.green, color.blue)
    return "#" + "".join(
        f"{round(max(0.0, min(1.0, channel)) * 255):02x}"
        for channel in channels
    )
