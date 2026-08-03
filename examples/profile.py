"""Reusable project profiles kept beside rendering scripts.

Copy this file into a project's ``render`` package and adapt it there. Nothing
in an installed atomic-povray package needs to be edited.
"""

from dataclasses import replace

from atomic_povray import (
    DEFAULT_PROFILE,
    AreaLight,
    Camera,
    Color,
    ElementOverride,
)


SIZE_FACTOR = 0.85
SURFACE_OXYGEN_COLOR = Color(1.00, 0.33, 0.00)

LEGACY_ELEMENTS = {
    "H": ElementOverride(radius=0.20 * SIZE_FACTOR, color=Color(0.90, 0.90, 0.90)),
    "C": ElementOverride(radius=0.40 * SIZE_FACTOR, color=Color(0.20, 0.20, 0.20)),
    "O": ElementOverride(radius=0.40 * SIZE_FACTOR, color=Color(1.05, 0.10, 0.05)),
    "Fe": ElementOverride(radius=0.65 * SIZE_FACTOR, color=Color(0.10, 0.10, 1.10)),
    "Rh": ElementOverride(radius=0.65 * SIZE_FACTOR, color=Color(0.50, 0.50, 0.50)),
    "Pt": ElementOverride(radius=0.75 * SIZE_FACTOR, color=Color(0.60, 0.60, 0.60)),
}

PROFILE = replace(
    DEFAULT_PROFILE,
    style=replace(
        DEFAULT_PROFILE.style,
        # The legacy radii above already contain their desired size scaling.
        preset_atom_size_scales={
            **DEFAULT_PROFILE.style.preset_atom_size_scales,
            "ball_and_stick": 1.0,
        },
        element_overrides=LEGACY_ELEMENTS,
    ),
    render=replace(DEFAULT_PROFILE.render, width=1200, height=900),
)

# Named variants can share the same geometry, element, and render defaults.
SIDE_PROFILE = replace(
    PROFILE,
    scene=replace(
        PROFILE.scene,
        camera_up=(0.0, 0.0, 1.0),
        camera_width=20.0,
    ),
)
TOP_PROFILE = replace(
    PROFILE,
    scene=replace(
        PROFILE.scene,
        camera_up=(0.0, 1.0, 0.0),
        camera_width=20.0,
    ),
)
PERSPECTIVE_PROFILE = replace(
    PROFILE,
    scene=replace(PROFILE.scene, camera_angle=30.0),
)


def legacy_light(camera: Camera) -> AreaLight:
    """Return the fixed soft area light from the legacy side-view scene."""

    defaults = SIDE_PROFILE.scene
    return AreaLight(
        location=(-4000.0, -6000.0, 6000.0),
        target=camera.target,
        intensity=defaults.light_intensity,
        angular_diameter=defaults.light_angular_diameter,
        samples=defaults.light_samples,
        adaptive=defaults.light_adaptive,
    )
