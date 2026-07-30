"""Generic, renderer-independent scene primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from .model import Vec3


@dataclass(frozen=True)
class Color:
    red: float
    green: float
    blue: float
    alpha: float = 1.0

    def __post_init__(self) -> None:
        if any(value < 0 for value in (self.red, self.green, self.blue)):
            raise ValueError("RGB color channels must be non-negative")
        if not 0 <= self.alpha <= 1:
            raise ValueError("Alpha must lie between 0 and 1")

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


@dataclass(frozen=True)
class Finish:
    """Color-independent POV-Ray finish shared by styled primitives."""

    ambient: float = 0.10
    diffuse: float = 0.60
    phong: float = 0.0
    phong_size: float = 10.0

    def material(self, color: Color) -> Material:
        """Combine this finish with a pigment color."""

        return Material(
            color=color,
            ambient=self.ambient,
            diffuse=self.diffuse,
            phong=self.phong,
            phong_size=self.phong_size,
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
class TriangleMeshPrimitive:
    """Generic triangle mesh hook for later hull/isosurface modules."""

    vertices: tuple[Vec3, ...]
    faces: tuple[tuple[int, int, int], ...]
    material: Material


Primitive: TypeAlias = SpherePrimitive | CylinderPrimitive | TriangleMeshPrimitive
