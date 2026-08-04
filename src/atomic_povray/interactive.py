"""Curated, asynchronous notebook controls for refining completed scenes."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, replace
from html import escape
from math import isclose
from pathlib import Path
import subprocess
import tempfile
from time import perf_counter
from typing import Any, Literal

from .backends.povray_sdl import (
    RenderConfig,
    RenderResult,
    _hidden_windows_process_kwargs,
    write_ini,
    write_scene,
)
from .model import GeometryModel
from .primitives import Color, Primitive
from .scene import AreaLight, Background, Camera, Fog, PointLight, Scene
from .styling import DepthShading, StyleConfig, apply_styles


ControlKind = Literal["boolean", "choice", "color", "number", "vector"]


@dataclass(frozen=True, init=False)
class Control:
    """Override presentation defaults for one registered interactive control."""

    name: str
    min: float | None
    max: float | None
    step: float | None
    label: str | None

    def __init__(
        self,
        name: str,
        *,
        min: float | None = None,
        max: float | None = None,
        step: float | None = None,
        label: str | None = None,
    ) -> None:
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "min", min)
        object.__setattr__(self, "max", max)
        object.__setattr__(self, "step", step)
        object.__setattr__(self, "label", label)


@dataclass(frozen=True)
class _InteractiveState:
    scene: Scene
    style_config: StyleConfig | None
    depth_shading: DepthShading
    fog: Fog


Getter = Callable[[_InteractiveState], Any]
Setter = Callable[[_InteractiveState, Any], _InteractiveState]
Applicability = Callable[[_InteractiveState], bool]


@dataclass(frozen=True)
class _ControlSpec:
    name: str
    kind: ControlKind
    label: str
    group: str
    getter: Getter
    setter: Setter
    minimum: float | None = None
    maximum: float | None = None
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
            return vector
        if isinstance(value, bool):
            raise TypeError(f"{self.name} must be a number")
        number = float(value)
        if self.minimum is not None and number < self.minimum:
            raise ValueError(f"{self.name} must be at least {self.minimum}")
        if self.maximum is not None and number > self.maximum:
            raise ValueError(f"{self.name} must be at most {self.maximum}")
        return number


def _with_scene(state: _InteractiveState, scene: Scene) -> _InteractiveState:
    return replace(state, scene=scene)


def _camera_spec(
    name: str,
    kind: ControlKind,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
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
        minimum, maximum, step, choices,
    )


def _scene_attribute_spec(
    name: str,
    kind: ControlKind,
    label: str,
    group: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    step: float | None = None,
) -> _ControlSpec:
    field_name = name.rsplit(".", 1)[1]

    def getter(state: _InteractiveState) -> Any:
        return getattr(state.scene, field_name)

    def setter(state: _InteractiveState, value: Any) -> _InteractiveState:
        return _with_scene(state, replace(state.scene, **{field_name: value}))

    return _ControlSpec(
        name, kind, label, group, getter, setter,
        minimum, maximum, step,
    )


def _style_attribute_spec(
    name: str,
    kind: ControlKind,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
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
        minimum, maximum, step, choices,
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
        0.0, 1.0, 0.05,
        applicable=lambda state: state.style_config is not None,
    )


def _depth_spec(
    name: str,
    kind: ControlKind,
    label: str,
    field_name: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
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
        minimum, maximum, step,
        applicable=lambda state: state.style_config is not None,
    )


def _first_light(state: _InteractiveState) -> PointLight | AreaLight:
    if not state.scene.lights:
        raise ValueError("the scene has no light to control")
    return state.scene.lights[0]


def _light_spec(
    name: str,
    kind: ControlKind,
    label: str,
    field_name: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
    step: float | None = None,
) -> _ControlSpec:
    def getter(state: _InteractiveState) -> Any:
        return getattr(_first_light(state), field_name)

    def setter(state: _InteractiveState, value: Any) -> _InteractiveState:
        lights = list(state.scene.lights)
        lights[0] = replace(_first_light(state), **{field_name: value})
        return _with_scene(state, replace(state.scene, lights=tuple(lights)))

    return _ControlSpec(
        name, kind, label, "Lighting", getter, setter,
        minimum, maximum, step,
        applicable=lambda state: bool(state.scene.lights),
    )


def _make_control_specs() -> dict[str, _ControlSpec]:
    specs = [
        _camera_spec("camera.direction", "vector", "Direction", step=0.1),
        _camera_spec("camera.target", "vector", "Target", step=0.1),
        _camera_spec("camera.up", "vector", "Up", step=0.1),
        _camera_spec(
            "camera.projection", "choice", "Projection",
            choices=("orthographic", "perspective"),
        ),
        _camera_spec(
            "camera.angle", "number", "Perspective angle",
            minimum=1.0, maximum=179.0, step=0.5,
        ),
        _camera_spec(
            "camera.width", "number", "Orthographic width",
            minimum=0.01, maximum=500.0, step=0.25,
        ),
        _scene_attribute_spec(
            "scene.ambient_light", "color", "Ambient light", "Scene"
        ),
        _light_spec("scene.light.location", "vector", "Location", "location", step=0.1),
        _light_spec("scene.light.color", "color", "Color", "color"),
        _light_spec(
            "scene.light.intensity", "number", "Intensity", "intensity",
            minimum=0.0, maximum=10.0, step=0.05,
        ),
        _style_attribute_spec(
            "style.preset_style", "choice", "Preset",
            choices=("ball_and_stick", "space_filling", "polyhedral"),
        ),
        _style_attribute_spec(
            "style.atom_size_scale", "number", "Atom size scale",
            minimum=0.01, maximum=5.0, step=0.05,
        ),
        _style_attribute_spec(
            "style.bond_size_scale", "number", "Bond size scale",
            minimum=0.01, maximum=5.0, step=0.05,
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
            "style.depth_shading.origin", "vector", "Origin", "origin", step=0.1
        ),
        _depth_spec(
            "style.depth_shading.direction",
            "vector",
            "Direction",
            "direction",
            step=0.1,
        ),
        _depth_spec(
            "style.depth_shading.decay_length",
            "number",
            "Decay length",
            "decay_length",
            minimum=0.01,
            maximum=500.0,
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
    for field_name, kind, label, minimum, maximum, step in (
        ("distance", "number", "Distance", 0.01, 1000.0, 0.5),
        ("color", "color", "Color", None, None, None),
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
                minimum,
                maximum,
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


def available_controls() -> tuple[str, ...]:
    """Return the stable names accepted by :func:`interactive_render`."""

    return tuple(_CONTROL_SPECS)


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


@dataclass(frozen=True)
class RenderTimings:
    generation: int
    full_quality: bool
    scene_export_s: float
    process_s: float
    total_s: float


@dataclass(frozen=True)
class InteractiveRenderResult:
    png: bytes
    timings: RenderTimings
    render_result: RenderResult


@dataclass(frozen=True)
class _RenderJob:
    generation: int
    scene: Scene
    config: RenderConfig
    full_quality: bool


class _LatestRenderController:
    """Serialize POV-Ray jobs while retaining only the latest pending state."""

    def __init__(
        self,
        *,
        output: Path,
        on_result: Callable[[InteractiveRenderResult], None],
        on_status: Callable[[str], None],
        debounce_s: float,
        max_wait_s: float,
    ) -> None:
        self.output = output
        self.on_result = on_result
        self.on_status = on_status
        self.debounce_s = debounce_s
        self.max_wait_s = max_wait_s
        self.generation = 0
        self.pending: _RenderJob | None = None
        self.worker: asyncio.Task[None] | None = None
        self.start_task: asyncio.Task[None] | None = None
        self.first_pending_at: float | None = None
        self.process: subprocess.Popen[bytes] | None = None
        self.last_error: str | None = None

    @property
    def is_rendering(self) -> bool:
        return self.worker is not None and not self.worker.done()

    def request(
        self,
        scene: Scene,
        config: RenderConfig,
        *,
        full_quality: bool = False,
        immediate: bool = False,
    ) -> int:
        self.generation += 1
        job = _RenderJob(self.generation, scene, config, full_quality)
        self.pending = job
        if self.is_rendering:
            self.on_status(
                f"rendering; request {job.generation} is pending"
            )
            return job.generation
        loop = asyncio.get_running_loop()
        now = loop.time()
        if self.first_pending_at is None:
            self.first_pending_at = now
        if self.start_task is not None:
            self.start_task.cancel()
        deadline = min(
            now + self.debounce_s,
            self.first_pending_at + self.max_wait_s,
        )
        delay = 0.0 if immediate else max(0.0, deadline - now)
        self.start_task = asyncio.create_task(self._start_after(delay))
        mode = "full-quality render" if full_quality else "preview"
        self.on_status(f"{mode} {job.generation} queued")
        return job.generation

    async def _start_after(self, delay: float) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        if not self.is_rendering and self.pending is not None:
            self.first_pending_at = None
            self.worker = asyncio.create_task(self._drain())

    async def _drain(self) -> None:
        try:
            while self.pending is not None:
                job = self.pending
                self.pending = None
                mode = "full quality" if job.full_quality else "preview"
                self.on_status(f"rendering {mode} {job.generation}")
                try:
                    result = await asyncio.to_thread(self._render_sync, job)
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    detail = str(error).strip() or type(error).__name__
                    self.last_error = f"{type(error).__name__}: {detail}"
                    self.on_status(f"render failed: {self.last_error}")
                    continue
                self.last_error = None
                self.on_result(result)
                timing = result.timings
                if job.generation == self.generation and self.pending is None:
                    self.on_status(
                        f"{mode} {job.generation}: {timing.total_s:.3f} s total "
                        f"({timing.scene_export_s:.3f} s export, "
                        f"{timing.process_s:.3f} s POV-Ray)"
                    )
                else:
                    self.on_status(
                        f"showing stale {mode} {job.generation}; "
                        f"request {self.generation} is pending"
                    )
        finally:
            self.process = None

    def _render_sync(self, job: _RenderJob) -> InteractiveRenderResult:
        total_start = perf_counter()
        temporary: tempfile.TemporaryDirectory[str] | None = None
        if job.full_quality:
            image_path = self.output
            image_path.parent.mkdir(parents=True, exist_ok=True)
            scene_path = image_path.with_suffix(".pov")
            ini_path = image_path.with_suffix(".ini")
        else:
            temporary = tempfile.TemporaryDirectory(
                prefix="atomic-povray-preview-"
            )
            job_dir = Path(temporary.name)
            image_path = job_dir / "preview.png"
            scene_path = job_dir / "preview.pov"
            ini_path = job_dir / "preview.ini"
        try:
            export_start = perf_counter()
            write_scene(
                job.scene,
                scene_path,
                width=job.config.width,
                height=job.config.height,
                povray_version=job.config.povray_version,
                max_trace_level=job.config.max_trace_level,
                radiosity=job.config.radiosity,
                additional_pov=job.config.additional_pov,
                profile=job.config.profile,
            )
            write_ini(
                scene_path,
                image_path,
                job.config,
                filename=ini_path,
            )
            export_s = perf_counter() - export_start
            executable_name = Path(job.config.executable).name.lower()
            if executable_name.startswith(("pvengine", "povwin")):
                command = (
                    job.config.executable,
                    "/NR",
                    "/RENDER",
                    ini_path.name,
                    "/EXIT",
                )
            else:
                command = (job.config.executable, ini_path.name)
            kwargs = (
                _hidden_windows_process_kwargs()
                if not job.config.display
                else {}
            )
            process_start = perf_counter()
            try:
                process = subprocess.Popen(
                    command,
                    cwd=image_path.parent.resolve(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    **kwargs,
                )
            except Exception as error:
                detail = str(error).strip() or type(error).__name__
                raise RuntimeError(
                    f"could not start POV-Ray ({type(error).__name__}: {detail}); "
                    f"command={command!r}"
                ) from error
            self.process = process
            try:
                stdout_bytes, stderr_bytes = process.communicate()
            finally:
                self.process = None
            process_s = perf_counter() - process_start
            stdout = stdout_bytes.decode(errors="replace")
            stderr = stderr_bytes.decode(errors="replace")
            if process.returncode != 0:
                detail = stderr.strip() or stdout.strip() or "no process output"
                raise RuntimeError(
                    f"POV-Ray exited with code {process.returncode}: {detail}; "
                    f"command={command!r}"
                )
            if not image_path.is_file() or image_path.stat().st_size == 0:
                raise RuntimeError(
                    "POV-Ray exited successfully but did not create a non-empty PNG; "
                    f"command={command!r}; stdout={stdout.strip()!r}; "
                    f"stderr={stderr.strip()!r}"
                )
            png = image_path.read_bytes()
            render_result = RenderResult(
                image_path=image_path,
                scene_path=scene_path,
                ini_path=ini_path,
                command=command,
                stdout=stdout,
                stderr=stderr,
            )
            timings = RenderTimings(
                job.generation,
                job.full_quality,
                export_s,
                process_s,
                perf_counter() - total_start,
            )
            return InteractiveRenderResult(png, timings, render_result)
        finally:
            if temporary is not None:
                temporary.cleanup()

    async def cancel(self) -> None:
        self.pending = None
        self.first_pending_at = None
        if self.start_task is not None:
            self.start_task.cancel()
        process = self.process
        if process is not None and process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(asyncio.to_thread(process.wait), 2.0)
            except TimeoutError:
                process.kill()
                await asyncio.to_thread(process.wait)
        if self.worker is not None and not self.worker.done():
            self.worker.cancel()
            try:
                await self.worker
            except asyncio.CancelledError:
                pass
        self.on_status("render cancelled")


class InteractiveRenderSession:
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

        resolved: list[Control] = []
        for value in controls:
            control = Control(value) if isinstance(value, str) else value
            if not isinstance(control, Control):
                raise TypeError("controls must contain strings or Control objects")
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
            if (
                control.min is not None
                and spec.minimum is not None
                and control.min < spec.minimum
            ):
                raise ValueError(
                    f"{control.name} min cannot be below the registered "
                    f"limit {spec.minimum}"
                )
            if (
                control.max is not None
                and spec.maximum is not None
                and control.max > spec.maximum
            ):
                raise ValueError(
                    f"{control.name} max cannot exceed the registered "
                    f"limit {spec.maximum}"
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
        for name, widget in self._control_widgets.items():
            if name.startswith("style.depth_shading.") and not name.endswith(
                ".enabled"
            ):
                self._set_widget_disabled(widget, not depth_enabled)
            elif name.startswith("scene.fog.") and not name.endswith(".enabled"):
                self._set_widget_disabled(widget, not fog_enabled)

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
    ) -> tuple[float, float, float]:
        step = control.step if control.step is not None else spec.step or 0.1
        default_span = max(10.0 * step, abs(current) * 2.0, 1.0)
        minimum = (
            control.min
            if control.min is not None
            else spec.minimum
            if spec.minimum is not None
            else current - default_span
        )
        maximum = (
            control.max
            if control.max is not None
            else spec.maximum
            if spec.maximum is not None
            else current + default_span
        )
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
            for index, (component, axis) in enumerate(zip(value, "xyz")):
                minimum, maximum, step = self._bounds(
                    control, spec, float(component)
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
        minimum, maximum, step = self._bounds(control, spec, float(value))
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


def _color_to_hex(color: Color) -> str:
    channels = (color.red, color.green, color.blue)
    return "#" + "".join(
        f"{round(max(0.0, min(1.0, channel)) * 255):02x}"
        for channel in channels
    )


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


__all__ = [
    "Control",
    "InteractiveRenderResult",
    "InteractiveRenderSession",
    "RenderTimings",
    "apply_interactive_values",
    "available_controls",
    "interactive_render",
]
