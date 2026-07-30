"""Camera, light, background, and complete scene configuration."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite, sqrt
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


def get_default_light(
    camera: Camera,
    *,
    intensity: float = 1.8,
    angular_diameter: float = 35.0,
    samples: tuple[int, int] = (9, 9),
    adaptive: int = 3,
) -> AreaLight:
    """Return a soft key light positioned above and right of the camera.

    The light starts at the camera location and is offset by half the camera
    distance along both the camera's corrected up direction and screen-right
    direction. This keeps the illumination consistent as the camera moves or
    rotates.
    """

    distance = sqrt(sum(component * component for component in camera.direction))
    if not isfinite(distance) or distance <= 0:
        raise ValueError("camera direction must be non-zero and finite")

    view = tuple(component / distance for component in camera.direction)
    right_raw = (
        view[1] * camera.up[2] - view[2] * camera.up[1],
        view[2] * camera.up[0] - view[0] * camera.up[2],
        view[0] * camera.up[1] - view[1] * camera.up[0],
    )
    right_length = sqrt(sum(component * component for component in right_raw))
    if not isfinite(right_length) or right_length <= 0:
        raise ValueError("camera up must be finite and not parallel to direction")
    right = tuple(component / right_length for component in right_raw)
    corrected_up = (
        right[1] * view[2] - right[2] * view[1],
        right[2] * view[0] - right[0] * view[2],
        right[0] * view[1] - right[1] * view[0],
    )

    offset = 0.5 * distance
    location = tuple(
        camera_component + offset * (right_component + up_component)
        for camera_component, right_component, up_component in zip(
            camera.location, right, corrected_up
        )
    )
    return AreaLight(
        location=location,
        target=camera.target,
        intensity=intensity,
        angular_diameter=angular_diameter,
        samples=samples,
        adaptive=adaptive,
    )


Light = PointLight | AreaLight


@dataclass(frozen=True)
class Background:
    color: Color = Color(1.0, 1.0, 1.0)


@dataclass(frozen=True)
class Fog:
    """POV-Ray's constant, camera-distance-based atmospheric fog."""

    distance: float
    color: Color = Color(1.0, 1.0, 1.0)

    def __post_init__(self) -> None:
        if not isfinite(self.distance) or self.distance <= 0:
            raise ValueError("fog distance must be positive and finite")


@dataclass(frozen=True)
class Scene:
    primitives: tuple[Primitive, ...]
    camera: Camera
    lights: tuple[Light, ...]
    background: Background
    ambient_light: Color = Color(1.0, 1.0, 1.0)
    fog: Fog | None = None


def make_scene(
    primitives: tuple[Primitive, ...],
    *,
    camera: Camera,
    lights: tuple[Light, ...] = (),
    background: Background | None = None,
    ambient_light: Color = Color(1.0, 1.0, 1.0),
    fog: Fog | None = None,
    extra_primitives: tuple[Primitive, ...] = (),
) -> Scene:
    """Assemble a scene; extras are a public extension point."""

    return Scene(
        primitives=(*primitives, *extra_primitives),
        camera=camera,
        lights=lights,
        background=background or Background(),
        ambient_light=ambient_light,
        fog=fog,
    )
