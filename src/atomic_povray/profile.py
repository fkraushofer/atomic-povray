"""Immutable, reusable defaults profiles for atomic-povray projects."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite
from numbers import Real
from types import MappingProxyType

from . import _defaults
from .model import Vec3
from .primitives import Color, Finish
from .radiosity import Radiosity


@dataclass(frozen=True)
class ElementOverride:
    """Optional profile-level radius and color for one chemical element."""

    radius: float | None = None
    color: Color | None = None

    def __post_init__(self) -> None:
        if self.radius is not None and (
            not isfinite(self.radius) or self.radius <= 0
        ):
            raise ValueError("element radius must be positive and finite")


@dataclass(frozen=True)
class GeometryDefaults:
    bond_scale: float = _defaults.DEFAULT_BOND_SCALE
    hydrogen_bond_max: float = _defaults.DEFAULT_HYDROGEN_BOND_MAX


@dataclass(frozen=True)
class StyleDefaults:
    preset_style: str = _defaults.DEFAULT_PRESET_STYLE
    preset_atom_size_scales: Mapping[str, float] = field(
        default_factory=lambda: _defaults.DEFAULT_PRESET_ATOM_SIZE_SCALES
    )
    atom_size_scale: float = _defaults.DEFAULT_ATOM_SIZE_SCALE
    bond_size_scale: float = _defaults.DEFAULT_BOND_SIZE_SCALE
    bond_radius: float = _defaults.DEFAULT_BOND_RADIUS
    hydrogen_bond_radius: float = _defaults.DEFAULT_HYDROGEN_BOND_RADIUS
    hydrogen_bond_color: Color = _defaults.DEFAULT_HYDROGEN_BOND_COLOR
    hydrogen_bond_line_style: str = _defaults.DEFAULT_HYDROGEN_BOND_LINE_STYLE
    hydrogen_bond_segments: int = _defaults.DEFAULT_HYDROGEN_BOND_SEGMENTS
    polyhedron_filter: float = _defaults.DEFAULT_POLYHEDRON_FILTER
    polyhedron_transmit: float = _defaults.DEFAULT_POLYHEDRON_TRANSMIT
    atom_finish: Finish = _defaults.DEFAULT_ATOM_FINISH
    bond_finish: Finish = _defaults.DEFAULT_BOND_FINISH
    polyhedron_finish: Finish = _defaults.DEFAULT_POLYHEDRON_FINISH
    element_overrides: Mapping[str, ElementOverride] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "preset_atom_size_scales",
            MappingProxyType(dict(self.preset_atom_size_scales)),
        )
        overrides = dict(self.element_overrides)
        if not all(
            isinstance(symbol, str) and isinstance(value, ElementOverride)
            for symbol, value in overrides.items()
        ):
            raise TypeError(
                "element_overrides must map symbols to ElementOverride values"
            )
        object.__setattr__(self, "element_overrides", MappingProxyType(overrides))


@dataclass(frozen=True)
class SceneDefaults:
    camera_direction: Vec3 | None = None
    camera_up: Vec3 = _defaults.DEFAULT_CAMERA_UP
    camera_angle: float = _defaults.DEFAULT_CAMERA_ANGLE
    camera_width: float = _defaults.DEFAULT_CAMERA_WIDTH
    light_intensity: float = _defaults.DEFAULT_LIGHT_INTENSITY
    light_angular_diameter: float = _defaults.DEFAULT_LIGHT_ANGULAR_DIAMETER
    light_samples: tuple[int, int] = _defaults.DEFAULT_LIGHT_SAMPLES
    light_adaptive: int = _defaults.DEFAULT_LIGHT_ADAPTIVE
    background_color: Color = _defaults.DEFAULT_BACKGROUND_COLOR
    ambient_light: Color | float = _defaults.DEFAULT_AMBIENT_LIGHT

    def __post_init__(self) -> None:
        ambient = self.ambient_light
        if isinstance(ambient, bool) or not isinstance(ambient, (Color, Real)):
            raise TypeError("ambient_light must be a Color or a real number")
        if isinstance(ambient, Real):
            if not isfinite(ambient) or ambient < 0:
                raise ValueError("scalar ambient_light must be non-negative and finite")
            object.__setattr__(self, "ambient_light", Color(*(float(ambient),) * 3))


@dataclass(frozen=True)
class LabelDefaults:
    offset: Vec3 = _defaults.DEFAULT_LABEL_OFFSET
    size: float = _defaults.DEFAULT_LABEL_SIZE
    thickness: float = _defaults.DEFAULT_LABEL_THICKNESS
    font: str = _defaults.DEFAULT_LABEL_FONT
    color: Color = _defaults.DEFAULT_LABEL_COLOR


@dataclass(frozen=True)
class RenderDefaults:
    width: int = _defaults.DEFAULT_RENDER_WIDTH
    height: int = _defaults.DEFAULT_RENDER_HEIGHT
    quality: int = _defaults.DEFAULT_RENDER_QUALITY
    antialias: bool = _defaults.DEFAULT_RENDER_ANTIALIAS
    antialias_threshold: float | None = _defaults.DEFAULT_RENDER_ANTIALIAS_THRESHOLD
    sampling_method: int | None = _defaults.DEFAULT_RENDER_SAMPLING_METHOD
    display_gamma: float | None = _defaults.DEFAULT_RENDER_DISPLAY_GAMMA
    file_gamma: float | None = _defaults.DEFAULT_RENDER_FILE_GAMMA
    transparent: bool = _defaults.DEFAULT_RENDER_TRANSPARENT
    display: bool = _defaults.DEFAULT_RENDER_DISPLAY
    executable: str = _defaults.DEFAULT_POVRAY_EXECUTABLE
    povray_version: str = _defaults.DEFAULT_POVRAY_VERSION
    max_trace_level: int | None = _defaults.DEFAULT_RENDER_MAX_TRACE_LEVEL
    radiosity: Radiosity | None = _defaults.DEFAULT_RENDER_RADIOSITY
    additional_pov: str | None = _defaults.DEFAULT_RENDER_ADDITIONAL_POV
    additional_ini: str | None = _defaults.DEFAULT_RENDER_ADDITIONAL_INI


@dataclass(frozen=True)
class AtomicPovrayProfile:
    """One portable set of project-wide atomic-povray defaults."""

    geometry: GeometryDefaults = field(default_factory=GeometryDefaults)
    style: StyleDefaults = field(default_factory=StyleDefaults)
    scene: SceneDefaults = field(default_factory=SceneDefaults)
    labels: LabelDefaults = field(default_factory=LabelDefaults)
    render: RenderDefaults = field(default_factory=RenderDefaults)


DEFAULT_PROFILE = AtomicPovrayProfile()
