"""Render one ASE-readable structure with atomic-povray defaults.

Run from the repository root, for example:

    python -m examples.render_file POSCAR
    python -m examples.render_file POSCAR --view a --up z
    python -m examples.render_file POSCAR --view -x

``-m`` takes a module name, so omit the ``.py`` suffix.
"""

from __future__ import annotations

from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from dataclasses import replace
from os import environ
from pathlib import Path
from shutil import which
from sys import argv

import numpy as np
from numpy.typing import NDArray

from atomic_povray import (
    Background,
    Camera,
    Color,
    DisplayBounds,
    GeometryModel,
    RenderConfig,
    StructureModel,
    StyleConfig,
    apply_styles,
    build_geometry,
    get_default_bonds,
    get_default_light,
    load_structure,
    make_scene,
    render_scene,
)


AXES = ("x", "y", "z", "a", "b", "c")
SIGNED_AXES = tuple(
    axis
    for unsigned_axis in AXES
    for axis in (unsigned_axis, f"-{unsigned_axis}")
)
FRACTIONAL_RANGES = ((0.0, 1.0), (0.0, 1.0), (0.0, 1.0))
CAMERA_DISTANCE = 100.0
CAMERA_MARGIN = 1.0
STYLE_CONFIG = StyleConfig()
RENDER_CONFIG = RenderConfig()
BACKGROUND = Background(Color(1.0, 1.0, 1.0))


class StructureReadError(ValueError):
    """Raised when ASE cannot read an input structure file."""


def resolve_povray_executable(povray: str | Path | None = None) -> str:
    """Resolve an explicit executable, ``POVRAY``, or ``povray`` on ``PATH``."""

    candidate = str(povray) if povray is not None else environ.get("POVRAY", "povray")
    resolved = which(candidate)
    if resolved is None:
        raise RuntimeError(
            f"Could not resolve the POV-Ray executable {candidate!r}. "
            "Pass its path with --povray PATH, set the POVRAY environment "
            "variable, or edit the executable choice in render_file.py."
        )
    return resolved


def direction_vector(axis: str, structure: StructureModel) -> NDArray[np.float64]:
    """Return a normalized Cartesian or lattice-vector direction."""

    sign = -1.0 if axis.startswith("-") else 1.0
    name = axis.removeprefix("-").lower()
    if name not in AXES:
        choices = ", ".join(SIGNED_AXES)
        raise ValueError(f"direction must be one of: {choices}")

    if name in ("x", "y", "z"):
        vector = np.eye(3, dtype=float)["xyz".index(name)]
    else:
        vector = structure.cell["abc".index(name)]
    length = float(np.linalg.norm(vector))
    if not np.isfinite(length) or length <= 0.0:
        raise ValueError(f"cannot use {axis!r}: the corresponding vector is zero")
    return sign * vector / length


def camera_axes(
    view: NDArray[np.float64],
    up_hint: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return normalized screen-right and corrected-up vectors."""

    right = np.cross(view, up_hint)
    right_length = float(np.linalg.norm(right))
    if not np.isfinite(right_length) or right_length < 1e-12:
        raise ValueError("camera view and up directions must not be parallel")
    right /= right_length
    corrected_up = np.cross(right, view)
    corrected_up /= np.linalg.norm(corrected_up)
    return right, corrected_up


def automatic_camera_width(
    geometry: GeometryModel,
    *,
    target: NDArray[np.float64],
    right: NDArray[np.float64],
    up: NDArray[np.float64],
    aspect_ratio: float,
) -> float:
    """Fit all displayed atoms into an orthographic view with a 1 Å margin."""

    positions = np.asarray([atom.position for atom in geometry.atoms], dtype=float)
    if not len(positions):
        raise ValueError("the selected display bounds contain no atoms")
    relative = positions - target
    horizontal_half_width = float(np.max(np.abs(relative @ right)))
    vertical_half_height = float(np.max(np.abs(relative @ up)))
    required_width = max(
        2.0 * horizontal_half_width,
        2.0 * vertical_half_height * aspect_ratio,
    )
    return max(2.0 * CAMERA_MARGIN, required_width + 2.0 * CAMERA_MARGIN)


def make_default_scene(
    input_path: str | Path,
    *,
    view: str = "x",
    up: str | None = None,
):
    """Build a default unit-cell scene and return it with its camera width."""

    try:
        structure = load_structure(input_path)
    except Exception as error:
        raise StructureReadError(
            f"{input_path!s} could not be read by ASE: {error}"
        ) from error
    if len(structure.atoms) == 0:
        raise ValueError(f"{input_path!s} contains no atoms")

    bond_rules = get_default_bonds(structure)
    geometry = build_geometry(
        structure,
        bond_rules=bond_rules,
        bounds=DisplayBounds(fractional_ranges=FRACTIONAL_RANGES),
    )
    styled = apply_styles(geometry, STYLE_CONFIG)

    view_vector = direction_vector(view, structure)
    up_name = up if up is not None else ("y" if view.removeprefix("-") == "z" else "z")
    up_vector = direction_vector(up_name, structure)
    right, corrected_up = camera_axes(view_vector, up_vector)

    target = np.asarray(structure.atoms.positions, dtype=float).mean(axis=0)
    aspect_ratio = RENDER_CONFIG.width / RENDER_CONFIG.height
    camera_width = automatic_camera_width(
        geometry,
        target=target,
        right=right,
        up=corrected_up,
        aspect_ratio=aspect_ratio,
    )
    camera = Camera.orthographic(
        direction=tuple(float(value) for value in view_vector * CAMERA_DISTANCE),
        target=tuple(float(value) for value in target),
        up=tuple(float(value) for value in up_vector),
        width=camera_width,
    )
    scene = make_scene(
        styled.primitives,
        camera=camera,
        lights=(get_default_light(camera),),
        background=BACKGROUND,
    )
    return scene, camera_width


def render_file(
    input_path: str | Path,
    *,
    output: str | Path | None = None,
    view: str = "x",
    up: str | None = None,
    povray: str | Path | None = None,
) -> Path:
    """Render one structure and return the output image path."""

    input_path = Path(input_path)
    output_path = Path(output) if output is not None else input_path.with_suffix(".png")
    executable = resolve_povray_executable(povray)
    scene, camera_width = make_default_scene(input_path, view=view, up=up)
    config = replace(RENDER_CONFIG, executable=executable)
    result = render_scene(scene, output_path, config)
    print(f"Rendered {result.image_path} (orthographic width {camera_width:.2f} Å)")
    return result.image_path


def add_camera_arguments(parser: ArgumentParser) -> None:
    """Add shared view, up, and executable options."""

    parser.add_argument(
        "--view",
        default="x",
        choices=SIGNED_AXES,
        help="view direction in Cartesian or unit-cell coordinates (default: x)",
    )
    parser.add_argument(
        "--up",
        default=None,
        choices=SIGNED_AXES,
        help="camera-up direction (default: z, or y for a ±z view)",
    )
    parser.add_argument(
        "--povray",
        metavar="PATH",
        help="POV-Ray executable; overrides the POVRAY environment variable",
    )


def build_parser() -> ArgumentParser:
    """Create the command-line parser."""

    parser = ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="ASE-readable structure file")
    parser.add_argument(
        "--output",
        type=Path,
        help="output image path (default: input name with .png suffix)",
    )
    add_camera_arguments(parser)
    return parser


def parse_arguments(
    parser: ArgumentParser,
    arguments: Sequence[str] | None = None,
) -> Namespace:
    """Parse arguments, accepting both ``--view -x`` and ``--view=-x``."""

    tokens = list(argv[1:] if arguments is None else arguments)
    normalized: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if (
            token in ("--view", "--up")
            and index + 1 < len(tokens)
            and tokens[index + 1] in SIGNED_AXES
            and tokens[index + 1].startswith("-")
        ):
            normalized.append(f"{token}={tokens[index + 1]}")
            index += 2
            continue
        normalized.append(token)
        index += 1
    return parser.parse_args(normalized)


def main() -> None:
    """Run the single-file command-line renderer."""

    parser = build_parser()
    arguments = parse_arguments(parser)
    try:
        render_file(
            arguments.input,
            output=arguments.output,
            view=arguments.view,
            up=arguments.up,
            povray=arguments.povray,
        )
    except (RuntimeError, ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
