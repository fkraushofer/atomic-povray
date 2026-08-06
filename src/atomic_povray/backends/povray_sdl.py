"""Direct declarative POV-Ray SDL backend."""

from __future__ import annotations

from dataclasses import dataclass
from math import radians, tan
from pathlib import Path
import subprocess
import sys
import warnings

import numpy as np

from ..model import Vec3
from ..primitives import (
    Color,
    CylinderPrimitive,
    Material,
    Primitive,
    SpherePrimitive,
    TextPrimitive,
    TriangleMeshPrimitive,
)
from ..profile import DEFAULT_PROFILE, AtomicPovrayProfile
from ..radiosity import Radiosity
from ..scene import AreaLight, Camera, PointLight, Scene


def _number(value: float) -> str:
    return f"{float(value):.9g}"


def _vector(vector: Vec3) -> str:
    return "<" + ", ".join(_number(value) for value in vector) + ">"


def _pigment(color: Color) -> str:
    channels = (
        f"{_number(color.red)}, {_number(color.green)}, {_number(color.blue)}"
    )
    if color.filter and color.transmit:
        value = f"rgbft <{channels}, {_number(color.filter)}, {_number(color.transmit)}>"
    elif color.filter:
        value = f"rgbf <{channels}, {_number(color.filter)}>"
    elif color.transmit:
        value = f"rgbt <{channels}, {_number(color.transmit)}>"
    else:
        value = f"rgb <{channels}>"
    return f"pigment {{ color {value} }}"


def _finish(material: Material) -> str:
    return (
        "finish { "
        f"ambient {_number(material.ambient)} "
        f"emission {_number(material.emission)} "
        f"diffuse {_number(material.diffuse)} "
        f"phong {_number(material.phong)} "
        f"phong_size {_number(material.phong_size)} "
        f"specular {_number(material.specular)}"
        " }"
    )


def _material(material: Material) -> str:
    return f"{_pigment(material.color)} {_finish(material)}"


def _quoted(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _text_matrix(primitive: TextPrimitive) -> str:
    right = primitive.right
    up = primitive.up
    normal = primitive.normal
    position = primitive.position
    values = (*right, *up, *normal, *position)
    return "<" + ", ".join(_number(value) for value in values) + ">"


def _primitive_to_sdl(primitive: Primitive) -> str:
    if isinstance(primitive, SpherePrimitive):
        return (
            f"sphere {{ {_vector(primitive.center)}, {_number(primitive.radius)} "
            f"{_material(primitive.material)} }}"
        )
    if isinstance(primitive, CylinderPrimitive):
        return (
            f"cylinder {{ {_vector(primitive.start)}, {_vector(primitive.end)}, "
            f"{_number(primitive.radius)} {_material(primitive.material)} }}"
        )
    if isinstance(primitive, TextPrimitive):
        return (
            'text { ttf '
            f'"{_quoted(primitive.font)}" "{_quoted(primitive.text)}" '
            f'{_number(primitive.thickness)}, 0 '
            f'{_material(primitive.material)} '
            f'scale {_number(primitive.size)} '
            f'matrix {_text_matrix(primitive)} }}'
        )
    if isinstance(primitive, TriangleMeshPrimitive):
        lines = ["mesh2 {"]
        lines.append(f"  vertex_vectors {{ {len(primitive.vertices)},")
        lines.extend(f"    {_vector(vertex)}," for vertex in primitive.vertices)
        lines.append("  }")
        if primitive.normals is not None:
            lines.append(f"  normal_vectors {{ {len(primitive.normals)},")
            lines.extend(f"    {_vector(normal)}," for normal in primitive.normals)
            lines.append("  }")
        lines.append(f"  face_indices {{ {len(primitive.faces)},")
        lines.extend(
            f"    <{face[0]}, {face[1]}, {face[2]}>,"
            for face in primitive.faces
        )
        lines.append("  }")
        if primitive.normals is not None:
            lines.append(f"  normal_indices {{ {len(primitive.faces)},")
            lines.extend(
                f"    <{face[0]}, {face[1]}, {face[2]}>,"
                for face in primitive.faces
            )
            lines.append("  }")
        lines.append(f"  {_material(primitive.material)}")
        lines.append("}")
        return "\n".join(lines)
    raise TypeError(f"Unsupported primitive type: {type(primitive).__name__}")


def _camera_to_sdl(camera: Camera, aspect_ratio: float) -> str:
    view = np.asarray(camera.direction, dtype=float)
    up_hint = np.asarray(camera.up, dtype=float)
    view /= np.linalg.norm(view)
    right = np.cross(view, up_hint)
    if np.linalg.norm(right) < 1e-12:
        raise ValueError("Camera up vector must not be parallel to the view direction")
    right /= np.linalg.norm(right)
    true_up = np.cross(right, view)
    true_up /= np.linalg.norm(true_up)

    lines = ["camera {"]
    if camera.projection == "orthographic":
        lines.append("  orthographic")
        right_vector = tuple(float(value) for value in right * camera.width)
        up_vector = tuple(
            float(value) for value in true_up * camera.width / aspect_ratio
        )
        lines.append(f"  right {_vector(right_vector)}")
        lines.append(f"  up {_vector(up_vector)}")
    else:
        lines.append(f"  angle {_number(camera.effective_angle)}")
        right_vector = tuple(float(value) for value in right * aspect_ratio)
        up_vector = tuple(float(value) for value in true_up)
        lines.append(f"  right {_vector(right_vector)}")
        lines.append(f"  up {_vector(up_vector)}")
    lines.extend(
        (
            f"  location {_vector(camera.location)}",
            f"  look_at {_vector(camera.target)}",
            f"  sky {_vector(camera.up)}",
            "}",
        )
    )
    return "\n".join(lines)


def _light_color(light: PointLight | AreaLight) -> tuple[float, float, float]:
    return tuple(
        channel * light.intensity
        for channel in (light.color.red, light.color.green, light.color.blue)
    )


def _area_light_axes(light: AreaLight) -> tuple[Vec3, Vec3]:
    location = np.asarray(light.location, dtype=float)
    target = np.asarray(light.target, dtype=float)
    direction = target - location
    distance = np.linalg.norm(direction)
    if distance < 1e-12:
        raise ValueError("Area-light target must differ from its location")
    direction /= distance

    reference = np.array((0.0, 0.0, 1.0))
    if abs(float(np.dot(direction, reference))) > 0.99:
        reference = np.array((0.0, 1.0, 0.0))
    axis_a = np.cross(direction, reference)
    axis_a /= np.linalg.norm(axis_a)
    axis_b = np.cross(direction, axis_a)
    side = 2.0 * distance * tan(radians(light.angular_diameter) / 2.0)
    return (
        tuple(float(value) for value in axis_a * side),
        tuple(float(value) for value in axis_b * side),
    )


def _light_to_sdl(light: PointLight | AreaLight) -> str:
    color = _light_color(light)
    if isinstance(light, PointLight):
        shadowless = " shadowless" if light.shadowless else ""
        return (
            f"light_source {{ {_vector(light.location)} color rgb "
            f"{_vector(color)}{shadowless} }}"
        )

    axis_a, axis_b = _area_light_axes(light)
    options = [f"adaptive {light.adaptive}"]
    if light.circular:
        options.append("circular")
    if light.orient:
        options.append("orient")
    if light.jitter:
        options.append("jitter")
    return "\n".join(
        (
            f"light_source {{ {_vector(light.location)} color rgb {_vector(color)}",
            f"  area_light {_vector(axis_a)}, {_vector(axis_b)}, "
            f"{light.samples[0]}, {light.samples[1]}",
            "  " + " ".join(options),
            "}",
        )
    )


def _validate_povray_version(value: str) -> str:
    parts = value.split(".")
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise ValueError("povray_version must have the form 'major.minor'")
    return value


def _radiosity_to_sdl(radiosity: Radiosity) -> list[str]:
    return [
        "  radiosity {",
        f"    pretrace_start {_number(radiosity.pretrace_start)}",
        f"    pretrace_end {_number(radiosity.pretrace_end)}",
        f"    count {radiosity.count}",
        f"    error_bound {_number(radiosity.error_bound)}",
        f"    recursion_limit {radiosity.recursion_limit}",
        "  }",
    ]


def _warn_for_radiosity_ambient(scene: Scene, radiosity: Radiosity | None) -> None:
    ambient_light_is_nonzero = any(
        channel != 0
        for channel in (
            scene.ambient_light.red,
            scene.ambient_light.green,
            scene.ambient_light.blue,
        )
    )
    if radiosity is not None and ambient_light_is_nonzero and any(
        primitive.material.ambient != 0 for primitive in scene.primitives
    ):
        warnings.warn(
            "Radiosity is enabled while one or more materials have ambient != 0. "
            "This can make indirect illumination look washed out; ambient=0 is "
            "usually a better starting point. Rendering will continue.",
            UserWarning,
            stacklevel=3,
        )


def scene_to_sdl(
    scene: Scene,
    *,
    aspect_ratio: float | None = None,
    povray_version: str | None = None,
    max_trace_level: int | None = None,
    radiosity: Radiosity | None = None,
    additional_pov: str | None = None,
    profile: AtomicPovrayProfile = DEFAULT_PROFILE,
) -> str:
    if aspect_ratio is None:
        aspect_ratio = profile.render.width / profile.render.height
    if povray_version is None:
        povray_version = profile.render.povray_version
    ambient = scene.ambient_light
    if radiosity is None:
        radiosity = profile.render.radiosity
    _warn_for_radiosity_ambient(scene, radiosity)
    povray_version = _validate_povray_version(povray_version)
    lines = [
        f"#version {povray_version};",
        "global_settings {",
        "  assumed_gamma 1.0",
        f"  ambient_light rgb <{_number(ambient.red)}, "
        f"{_number(ambient.green)}, {_number(ambient.blue)}>",
    ]
    if max_trace_level is not None:
        if not isinstance(max_trace_level, int) or isinstance(max_trace_level, bool):
            raise TypeError("max_trace_level must be an integer")
        if max_trace_level < 1:
            raise ValueError("max_trace_level must be positive")
        lines.append(f"  max_trace_level {max_trace_level}")
    if radiosity is not None:
        lines.extend(_radiosity_to_sdl(radiosity))
    lines.extend(("}", ""))
    if additional_pov:
        lines.extend((additional_pov.rstrip("\n"), ""))
    lines.extend(
        (
            _camera_to_sdl(scene.camera, aspect_ratio),
            "",
            f"background {{ color rgbf <{_number(scene.background.color.red)}, "
        f"{_number(scene.background.color.green)}, "
        f"{_number(scene.background.color.blue)}, "
            f"{_number(1.0 - scene.background.color.alpha)}> }}",
        )
    )
    if scene.fog is not None:
        fog = scene.fog
        lines.extend(
            (
                "",
                "fog {",
                "  fog_type 1",
                f"  distance {_number(fog.distance)}",
                f"  color rgbf <{_number(fog.color.red)}, "
                f"{_number(fog.color.green)}, {_number(fog.color.blue)}, "
                f"{_number(1.0 - fog.color.alpha)}>",
                "}",
            )
        )
    lines.extend(_light_to_sdl(light) for light in scene.lights)
    lines.append("")
    lines.extend(_primitive_to_sdl(primitive) for primitive in scene.primitives)
    lines.append("")
    return "\n".join(lines)


def write_scene(
    scene: Scene,
    filename: str | Path,
    *,
    width: int | None = None,
    height: int | None = None,
    povray_version: str | None = None,
    max_trace_level: int | None = None,
    radiosity: Radiosity | None = None,
    additional_pov: str | None = None,
    profile: AtomicPovrayProfile = DEFAULT_PROFILE,
) -> Path:
    width = profile.render.width if width is None else width
    height = profile.render.height if height is None else height
    povray_version = (
        profile.render.povray_version if povray_version is None else povray_version
    )
    path = Path(filename)
    path.write_text(
        scene_to_sdl(
            scene,
            aspect_ratio=width / height,
            povray_version=povray_version,
            max_trace_level=max_trace_level,
            radiosity=radiosity,
            additional_pov=additional_pov,
            profile=profile,
        ),
        encoding="utf-8",
    )
    return path


@dataclass(frozen=True)
class RenderConfig:
    width: int | None = None
    height: int | None = None
    quality: int | None = None
    antialias: bool | None = None
    antialias_threshold: float | None = None
    sampling_method: int | None = None
    display_gamma: float | None = None
    file_gamma: float | None = None
    transparent: bool | None = None
    display: bool | None = None
    executable: str | None = None
    povray_version: str | None = None
    max_trace_level: int | None = None
    radiosity: Radiosity | None = None
    additional_pov: str | None = None
    additional_ini: str | None = None
    profile: AtomicPovrayProfile = DEFAULT_PROFILE

    def __post_init__(self) -> None:
        defaults = self.profile.render
        for name in (
            "width",
            "height",
            "quality",
            "antialias",
            "antialias_threshold",
            "sampling_method",
            "display_gamma",
            "file_gamma",
            "transparent",
            "display",
            "executable",
            "povray_version",
            "max_trace_level",
            "radiosity",
            "additional_pov",
            "additional_ini",
        ):
            if getattr(self, name) is None:
                object.__setattr__(self, name, getattr(defaults, name))
        if self.width < 1 or self.height < 1:
            raise ValueError("Render width and height must be positive")
        if not 0 <= self.quality <= 11:
            raise ValueError("POV-Ray quality must lie between 0 and 11")
        if self.antialias_threshold is not None and self.antialias_threshold <= 0:
            raise ValueError("antialias_threshold must be positive")
        if self.sampling_method not in (None, 1, 2, 3):
            raise ValueError("sampling_method must be 1, 2, or 3")
        if self.display_gamma is not None and self.display_gamma <= 0:
            raise ValueError("display_gamma must be positive")
        if self.file_gamma is not None and self.file_gamma <= 0:
            raise ValueError("file_gamma must be positive")
        if self.max_trace_level is not None:
            if not isinstance(self.max_trace_level, int) or isinstance(
                self.max_trace_level, bool
            ):
                raise TypeError("max_trace_level must be an integer")
            if self.max_trace_level < 1:
                raise ValueError("max_trace_level must be positive")
        _validate_povray_version(self.povray_version)


@dataclass(frozen=True)
class RenderResult:
    image_path: Path
    scene_path: Path
    ini_path: Path
    command: tuple[str, ...]
    stdout: str
    stderr: str


def write_ini(
    scene_path: str | Path,
    image_path: str | Path,
    config: RenderConfig | None = None,
    *,
    filename: str | Path | None = None,
) -> Path:
    """Write POV-Ray render settings without starting the renderer."""

    config = config or RenderConfig()
    scene_path = Path(scene_path)
    image_path = Path(image_path)
    ini_path = Path(filename) if filename is not None else image_path.with_suffix(".ini")
    ini_path.parent.mkdir(parents=True, exist_ok=True)
    values: dict[str, object] = {
        "Input_File_Name": str(scene_path.resolve()),
        "Output_File_Name": str(image_path.resolve()),
        "Width": config.width,
        "Height": config.height,
        "Quality": config.quality,
        "Display": "On" if config.display else "Off",
        "Antialias": "On" if config.antialias else "Off",
        "Output_File_Type": "N",
        "Output_Alpha": "On" if config.transparent else "Off",
    }
    optional_values = {
        "Antialias_Threshold": config.antialias_threshold,
        "Sampling_Method": config.sampling_method,
        "Display_Gamma": config.display_gamma,
        "File_Gamma": config.file_gamma,
    }
    values.update(
        (key, value) for key, value in optional_values.items() if value is not None
    )
    lines = [f"{key}={value}" for key, value in values.items()]
    if config.additional_ini:
        lines.append(config.additional_ini.rstrip("\n"))
    ini_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return ini_path


def render_scene(
    scene: Scene,
    output: str | Path,
    config: RenderConfig | None = None,
    *,
    cleanup: bool = False,
) -> RenderResult:
    """Write and render a scene with POV-Ray.

    When ``cleanup`` is true, remove the generated scene and INI files after a
    successful render. Failed renders retain both files for inspection.
    """

    config = config or RenderConfig()
    if scene.fog is not None and config.quality < 9:
        warnings.warn(
            "POV-Ray fog requires quality 9 or higher and will not be rendered "
            f"at quality {config.quality}. Low quality remains useful for "
            "preview renders.",
            UserWarning,
            stacklevel=2,
        )
    image_path = Path(output)
    image_path.parent.mkdir(parents=True, exist_ok=True)
    scene_path = image_path.with_suffix(".pov")
    write_scene(
        scene,
        scene_path,
        width=config.width,
        height=config.height,
        povray_version=config.povray_version,
        max_trace_level=config.max_trace_level,
        radiosity=config.radiosity,
        additional_pov=config.additional_pov,
    )
    ini_path = write_ini(scene_path, image_path, config)

    executable_name = Path(config.executable).name.lower()
    if executable_name.startswith(("pvengine", "povwin")):
        command = (config.executable, "/RENDER", ini_path.name, "/EXIT")
    else:
        command = (config.executable, ini_path.name)
    process_kwargs = _hidden_windows_process_kwargs() if not config.display else {}
    completed = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        cwd=image_path.parent.resolve(),
        **process_kwargs,
    )
    result = RenderResult(
        image_path,
        scene_path,
        ini_path,
        command,
        completed.stdout,
        completed.stderr,
    )
    if cleanup:
        scene_path.unlink()
        ini_path.unlink()
    return result


def _hidden_windows_process_kwargs() -> dict[str, object]:
    """Return subprocess options that hide the POV-Ray application on Windows."""
    if sys.platform != "win32":
        return {}

    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startupinfo.wShowWindow = subprocess.SW_HIDE
    return {
        "startupinfo": startupinfo,
        "creationflags": subprocess.CREATE_NO_WINDOW,
    }
