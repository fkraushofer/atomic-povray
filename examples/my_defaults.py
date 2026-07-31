"""Reusable project-specific appearance defaults.

These reproduce the colors, atom sizes, finish, and lighting used by the
pre-package ("legacy") atomic POV-Ray setup.
"""

from collections.abc import Iterable

from atomic_povray import AreaLight, AtomStyle, Camera, Color, Finish


SIZE_FACTOR = 0.85
COLORS = {
    "H": Color(0.90, 0.90, 0.90),
    "C": Color(0.20, 0.20, 0.20),
    "O": Color(1.05, 0.10, 0.05),
    "Fe": Color(0.10, 0.10, 1.10),
    "Rh": Color(0.50, 0.50, 0.50),
    "Pt": Color(0.60, 0.60, 0.60),
}
SURFACE_OXYGEN_COLOR = Color(1.00, 0.33, 0.00)
RADII = {
    "H": 0.20 * SIZE_FACTOR,
    "C": 0.40 * SIZE_FACTOR,
    "O": 0.40 * SIZE_FACTOR,
    "Fe": 0.65 * SIZE_FACTOR,
    "Rh": 0.65 * SIZE_FACTOR,
    "Pt": 0.75 * SIZE_FACTOR,
}
ATOM_FINISH = Finish(ambient=0.10, diffuse=0.60, phong=0.30, phong_size=10)
AMBIENT_SCALE = 1.0


def atom_styles(symbols: Iterable[str]) -> dict[str, AtomStyle]:
    """Return legacy styles for the requested supported element symbols."""

    return {
        symbol: AtomStyle(
            radius=RADII[symbol],
            color=COLORS[symbol],
            finish=ATOM_FINISH,
        )
        for symbol in set(symbols)
        if symbol in RADII
    }


def legacy_light(camera: Camera) -> AreaLight:
    """Return the fixed soft area light from the legacy side-view scene."""

    return AreaLight(
        location=(-4000.0, -6000.0, 6000.0),
        target=camera.target,
        intensity=1.8,
        angular_diameter=35.0,
        samples=(9, 9),
        adaptive=3,
    )
