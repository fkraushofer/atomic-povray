"""Camera, light, background, and complete scene configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .model import Vec3
from .primitives import Color, Primitive


@dataclass(frozen=True)
class Camera:
    location: Vec3
    target: Vec3
    up: Vec3 = (0.0, 1.0, 0.0)
    projection: Literal["perspective", "orthographic"] = "perspective"
    angle: float = 35.0
    width: float = 20.0

    @classmethod
    def perspective(
        cls,
        *,
        location: Vec3,
        target: Vec3,
        up: Vec3 = (0.0, 1.0, 0.0),
        angle: float = 35.0,
    ) -> "Camera":
        return cls(location, target, up, "perspective", angle=angle)

    @classmethod
    def orthographic(
        cls,
        *,
        location: Vec3,
        target: Vec3,
        up: Vec3 = (0.0, 1.0, 0.0),
        width: float = 20.0,
    ) -> "Camera":
        return cls(location, target, up, "orthographic", width=width)


@dataclass(frozen=True)
class PointLight:
    location: Vec3
    color: Color = Color(1.0, 1.0, 1.0)
    intensity: float = 1.0
    shadowless: bool = False


@dataclass(frozen=True)
class Background:
    color: Color = Color(1.0, 1.0, 1.0)


@dataclass(frozen=True)
class Scene:
    primitives: tuple[Primitive, ...]
    camera: Camera
    lights: tuple[PointLight, ...]
    background: Background


def make_scene(
    primitives: tuple[Primitive, ...],
    *,
    camera: Camera,
    lights: tuple[PointLight, ...] = (),
    background: Background | None = None,
    extra_primitives: tuple[Primitive, ...] = (),
) -> Scene:
    """Assemble a scene; extras are a public extension point."""

    return Scene(
        primitives=(*primitives, *extra_primitives),
        camera=camera,
        lights=lights,
        background=background or Background(),
    )

