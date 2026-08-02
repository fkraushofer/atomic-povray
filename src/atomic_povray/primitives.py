"""Generic, renderer-independent scene primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from .model import Vec3


@dataclass(frozen=True, init=False)
class Color:
    red: float
    green: float
    blue: float
    filter: float
    transmit: float

    def __init__(
        self,
        red: float,
        green: float,
        blue: float,
        alpha: float | None = None,
        *,
        filter: float = 0.0,
        transmit: float | None = None,
    ) -> None:
        if alpha is not None and transmit is not None:
            raise ValueError("alpha and transmit are aliases; pass only one")
        if alpha is not None and not 0 <= alpha <= 1:
            raise ValueError("Alpha must lie between 0 and 1")
        resolved_transmit = (
            0.0 if alpha is None and transmit is None
            else 1.0 - alpha if alpha is not None
            else transmit
        )
        object.__setattr__(self, "red", red)
        object.__setattr__(self, "green", green)
        object.__setattr__(self, "blue", blue)
        object.__setattr__(self, "filter", filter)
        object.__setattr__(self, "transmit", resolved_transmit)
        self._validate()

    def _validate(self) -> None:
        if any(value < 0 for value in (self.red, self.green, self.blue)):
            raise ValueError("RGB color channels must be non-negative")
        if not 0 <= self.filter <= 1:
            raise ValueError("filter must lie between 0 and 1")
        if not 0 <= self.transmit <= 1:
            raise ValueError("transmit must lie between 0 and 1")

    @property
    def alpha(self) -> float:
        """Conventional opacity, retained as an alias of 1 - transmit."""

        return 1.0 - self.transmit

    def as_tuple(self) -> tuple[float, float, float, float]:
        return self.red, self.green, self.blue, self.alpha

    @classmethod
    def from_hex(cls, value: str, *, alpha: float = 1.0) -> "Color":
        text = value.removeprefix("#")
        if len(text) != 6:
            raise ValueError("Hex colors must have exactly six digits")
        return cls(
            *(int(text[index : index + 2], 16) / 255 for index in (0, 2, 4)),
            alpha,
        )


@dataclass(frozen=True)
class Material:
    color: Color
    ambient: float = 0.10
    diffuse: float = 0.60
    phong: float = 0.0
    phong_size: float = 10.0
    specular: float = 0.0
    emission: float = 0.0


@dataclass(frozen=True)
class Finish:
    """Color-independent POV-Ray finish shared by styled primitives."""

    ambient: float = 0.10
    diffuse: float = 0.60
    phong: float = 0.0
    phong_size: float = 10.0
    specular: float = 0.0
    emission: float = 0.0

    def material(self, color: Color) -> Material:
        """Combine this finish with a pigment color."""

        return Material(
            color=color,
            ambient=self.ambient,
            emission=self.emission,
            diffuse=self.diffuse,
            phong=self.phong,
            phong_size=self.phong_size,
            specular=self.specular,
        )


@dataclass(frozen=True)
class SpherePrimitive:
    center: Vec3
    radius: float
    material: Material


@dataclass(frozen=True)
class CylinderPrimitive:
    start: Vec3
    end: Vec3
    radius: float
    material: Material


@dataclass(frozen=True)
class TextPrimitive:
    """Camera-oriented TrueType text in world coordinates."""

    text: str
    position: Vec3
    right: Vec3
    up: Vec3
    normal: Vec3
    material: Material
    font: str = "timrom.ttf"
    size: float = 0.4
    thickness: float = 0.02


@dataclass(frozen=True)
class TriangleMeshPrimitive:
    """Generic triangle mesh hook for external hull/isosurface modules."""

    vertices: tuple[Vec3, ...]
    faces: tuple[tuple[int, int, int], ...]
    material: Material
    normals: tuple[Vec3, ...] | None = None
    reference_position: Vec3 | None = None

    def __post_init__(self) -> None:
        if self.normals is not None and len(self.normals) != len(self.vertices):
            raise ValueError("Triangle mesh normals must match the vertex count")


Primitive: TypeAlias = (
    SpherePrimitive | CylinderPrimitive | TextPrimitive | TriangleMeshPrimitive
)
