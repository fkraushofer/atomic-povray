"""Project-specific defaults for the hematite side-view notebook."""

from dataclasses import replace

from atomic_povray import (
    DEFAULT_PROFILE,
    AreaLight,
    Camera,
    Color,
    ElementOverride,
)


SIZE_FACTOR = 0.7

ELEMENT_OVERRIDES = {
    "H": ElementOverride(radius=0.20, color=Color(0.90, 0.90, 0.90)),
    "C": ElementOverride(radius=0.40, color=Color(0.20, 0.20, 0.20)),
    "O": ElementOverride(radius=0.40, color=Color(1.05, 0.10, 0.05)),
    "Fe": ElementOverride(radius=0.65, color=Color(0.10, 0.10, 1.10)),
    "Rh": ElementOverride(radius=0.65, color=Color(0.50, 0.50, 0.50)),
    "Pt": ElementOverride(radius=0.75, color=Color(0.60, 0.60, 0.60)),
}

HEMATITE_SIDE_VIEW = replace(
    DEFAULT_PROFILE,
    style=replace(
        DEFAULT_PROFILE.style,
        atom_size_scale=SIZE_FACTOR,
        element_overrides=ELEMENT_OVERRIDES,
    ),
    scene=replace(
        DEFAULT_PROFILE.scene,
        camera_direction=(0.0, 100.0, 0.0),
        camera_up=(0.0, 0.0, 1.0),
        camera_width=18.0,
    ),
    render=replace(
        width=1024,
        height=768,
        antialias_threshold=0.05,    # slower than default 0.1, but looks nicer
        sampling_method=2,
        display_gamma=2.0,
        file_gamma=2.0,
        transparent=True,
    ),
)


def get_side_view_light(camera: Camera) -> AreaLight:
    """Return the fixed soft area light used for the hematite side view."""

    defaults = HEMATITE_SIDE_VIEW.scene
    return AreaLight(
        location=(-4000.0, -6000.0, 6000.0),
        target=camera.target,
        intensity=defaults.light_intensity,
        angular_diameter=defaults.light_angular_diameter,
        samples=defaults.light_samples,
        adaptive=defaults.light_adaptive,
    )
