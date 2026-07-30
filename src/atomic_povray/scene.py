"""Camera, light, background, and complete scene configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .model import Vec3
from .primitives import Color, Primitive


@dataclass(frozen=True)
class Camera:
    direction: Vec3
    target: Vec3
    up: Vec3 = (0.0, 1.0, 0.0)
    projection: Literal["perspective", "orthographic"] = "perspective"
    angle: float = 35.0
    width: float = 20.0

    @property
    def location(self) -> Vec3:
        """Return the camera position derived from its target and direction."""

        return tuple(
            float(target - direction)
            for target, direction in zip(self.target, self.direction)
        )

    @classmethod
    def perspective(
        cls,
        *,
        direction: Vec3,
        target: Vec3,
        up: Vec3 = (0.0, 1.0, 0.0),
        angle: float = 35.0,
    ) -> "Camera":
        return cls(direction, target, up, "perspective", angle=angle)

    @classmethod
    def orthographic(
        cls,
        *,
        direction: Vec3,
        target: Vec3,
        up: Vec3 = (0.0, 1.0, 0.0),
        width: float = 20.0,
    ) -> "Camera":
        return cls(direction, target, up, "orthographic", width=width)


@dataclass(frozen=True)
class PointLight:
    location: Vec3
    color: Color = Color(1.0, 1.0, 1.0)
    intensity: float = 1.0
    shadowless: bool = False


@dataclass(frozen=True)
class AreaLight:
    """A square soft light specified by its angular diameter at a target."""

    location: Vec3
    target: Vec3 = (0.0, 0.0, 0.0)
    color: Color = Color(1.0, 1.0, 1.0)
    intensity: float = 1.0
    angular_diameter: float = 35.0
    samples: tuple[int, int] = (9, 9)
    adaptive: int = 2
    circular: bool = False
    orient: bool = True
    jitter: bool = False

    def __post_init__(self) -> None:
        if not 0 < self.angular_diameter < 180:
            raise ValueError("angular_diameter must lie between 0 and 180 degrees")
        if len(self.samples) != 2 or any(sample < 1 for sample in self.samples):
            raise ValueError("samples must contain two positive integers")
        if self.adaptive < 0:
            raise ValueError("adaptive must be non-negative")


Light = PointLight | AreaLight


@dataclass(frozen=True)
class Background:
    color: Color = Color(1.0, 1.0, 1.0)


@dataclass(frozen=True)
class Scene:
    primitives: tuple[Primitive, ...]
    camera: Camera
    lights: tuple[Light, ...]
    background: Background
    ambient_light: Color = Color(1.0, 1.0, 1.0)


def make_scene(
    primitives: tuple[Primitive, ...],
    *,
    camera: Camera,
    lights: tuple[Light, ...] = (),
    background: Background | None = None,
    ambient_light: Color = Color(1.0, 1.0, 1.0),
    extra_primitives: tuple[Primitive, ...] = (),
) -> Scene:
    """Assemble a scene; extras are a public extension point."""

    return Scene(
        primitives=(*primitives, *extra_primitives),
        camera=camera,
        lights=lights,
        background=background or Background(),
        ambient_light=ambient_light,
    )
