"""Camera, light, background, and complete scene configuration."""

from __future__ import annotations

import numpy as np

from dataclasses import dataclass
from math import isfinite
from numbers import Real
from typing import Literal

from ._defaults import (
    DEFAULT_AMBIENT_LIGHT,
    DEFAULT_BACKGROUND_COLOR,
    DEFAULT_CAMERA_UP,
    DEFAULT_CAMERA_WIDTH,
)
from .model import Vec3
from .primitives import Color, Primitive
from .profile import DEFAULT_PROFILE, AtomicPovrayProfile


@dataclass(frozen=True)
class Camera:
    direction: Vec3
    target: Vec3
    up: Vec3 = DEFAULT_CAMERA_UP
    projection: Literal["perspective", "orthographic"] = "perspective"
    angle: float | None = None
    width: float = DEFAULT_CAMERA_WIDTH

    @property
    def location(self) -> Vec3:
        """Return the camera position derived from its target and direction."""

        return tuple(
            float(target - direction)
            for target, direction in zip(self.target, self.direction)
        )

    @property
    def effective_angle(self) -> float:
        """Return the explicit or width-derived horizontal field of view."""

        if self.angle is not None:
            return self.angle
        distance = float(np.linalg.norm(self.direction))
        return float(np.degrees(2.0 * np.arctan(self.width / (2.0 * distance))))

    @classmethod
    def perspective(
        cls,
        *,
        direction: Vec3 | None = None,
        target: Vec3,
        up: Vec3 | None = None,
        width: float | None = None,
        angle: float | None = None,
        profile: AtomicPovrayProfile = DEFAULT_PROFILE,
    ) -> "Camera":
        defaults = profile.scene
        if direction is None:
            direction = defaults.camera_direction
        if direction is None:
            raise ValueError("direction must be passed or defined by the profile")
        return cls(
            direction,
            target,
            defaults.camera_up if up is None else up,
            "perspective",
            angle=defaults.camera_angle if angle is None else angle,
            width=defaults.camera_width if width is None else width,
        )

    @classmethod
    def orthographic(
        cls,
        *,
        direction: Vec3 | None = None,
        target: Vec3,
        up: Vec3 | None = None,
        width: float | None = None,
        profile: AtomicPovrayProfile = DEFAULT_PROFILE,
    ) -> "Camera":
        defaults = profile.scene
        if direction is None:
            direction = defaults.camera_direction
        if direction is None:
            raise ValueError("direction must be passed or defined by the profile")
        return cls(
            direction,
            target,
            defaults.camera_up if up is None else up,
            "orthographic",
            width=defaults.camera_width if width is None else width,
        )


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
    intensity: float | None = None,
    angular_diameter: float | None = None,
    samples: tuple[int, int] | None = None,
    adaptive: int | None = None,
    profile: AtomicPovrayProfile = DEFAULT_PROFILE,
) -> AreaLight:
    """Return a soft key light positioned above and right of the camera.

    The light starts at the camera location and is offset by half the camera
    distance along both the camera's corrected up direction and screen-right
    direction. This keeps the illumination consistent as the camera moves or
    rotates.
    """

    defaults = profile.scene
    distance = float(np.linalg.norm(camera.direction))
    if not isfinite(distance) or distance <= 0:
        raise ValueError("camera direction must be non-zero and finite")

    view = tuple(component / distance for component in camera.direction)
    right_raw = (
        view[1] * camera.up[2] - view[2] * camera.up[1],
        view[2] * camera.up[0] - view[0] * camera.up[2],
        view[0] * camera.up[1] - view[1] * camera.up[0],
    )
    right_length = float(np.linalg.norm(right_raw))
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
        intensity=defaults.light_intensity if intensity is None else intensity,
        angular_diameter=(
            defaults.light_angular_diameter
            if angular_diameter is None
            else angular_diameter
        ),
        samples=defaults.light_samples if samples is None else samples,
        adaptive=defaults.light_adaptive if adaptive is None else adaptive,
    )


Light = PointLight | AreaLight


@dataclass(frozen=True)
class Background:
    color: Color = DEFAULT_BACKGROUND_COLOR


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
    ambient_light: Color = DEFAULT_AMBIENT_LIGHT
    fog: Fog | None = None


def make_scene(
    primitives: tuple[Primitive, ...],
    *,
    camera: Camera,
    lights: tuple[Light, ...] = (),
    background: Background | None = None,
    ambient_light: Color | float | None = None,
    fog: Fog | None = None,
    extra_primitives: tuple[Primitive, ...] = (),
    profile: AtomicPovrayProfile = DEFAULT_PROFILE,
) -> Scene:
    """Assemble a scene; extras are a public extension point.

    A scalar ``ambient_light`` is shorthand for a neutral grey color.
    """

    if ambient_light is None:
        ambient_light = profile.scene.ambient_light
    if isinstance(ambient_light, bool) or not isinstance(
        ambient_light, (Color, Real)
    ):
        raise TypeError("ambient_light must be a Color or a real number")
    if isinstance(ambient_light, Real):
        if not isfinite(ambient_light) or ambient_light < 0:
            raise ValueError("scalar ambient_light must be non-negative and finite")
        ambient_light = Color(*(float(ambient_light),) * 3)

    return Scene(
        primitives=(*primitives, *extra_primitives),
        camera=camera,
        lights=lights,
        background=background or Background(profile.scene.background_color),
        ambient_light=ambient_light,
        fog=fog,
    )
