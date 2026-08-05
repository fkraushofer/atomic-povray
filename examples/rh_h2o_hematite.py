"""Render hydrated Rh/hematite with an imported project profile.

Run from the repository root with ``python -m examples.rh_h2o_hematite``.
Generated files are written to the current working directory by default. Use
``--output`` to choose another location and ``--no-render`` to write only the
POV-Ray scene.
"""

from argparse import ArgumentParser
from os import environ
from pathlib import Path
from shutil import which

import numpy as np

from atomic_povray import (
    AtomSelectionRule,
    AtomStyleOverride,
    Camera,
    DisplayBounds,
    RenderConfig,
    StyleConfig,
    apply_styles,
    build_geometry,
    get_default_bonds,
    load_structure,
    make_scene,
    render_scene,
    write_scene,
)

if __package__:
    from .hematite_profile import (
        HEMATITE_SIDE_VIEW,
        SURFACE_OXYGEN_COLOR,
        get_side_view_light,
    )
else:
    from hematite_profile import (
        HEMATITE_SIDE_VIEW,
        SURFACE_OXYGEN_COLOR,
        get_side_view_light,
    )


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "tests" / "data" / "rh-h2o-hematite.vasp"
DEFAULT_OUTPUT = "rh_h2o_hematite.png"
QUALITY = 5  # Use 3 for a quick preview.


def resolve_povray_executable(povray: str | Path | None = None) -> str:
    """Resolve an explicit path, ``POVRAY``, or ``povray`` on ``PATH``."""

    candidate = str(povray) if povray is not None else environ.get("POVRAY", "povray")
    resolved = which(candidate)
    if resolved is None:
        raise RuntimeError(
            f"Could not resolve the POV-Ray executable {candidate!r}. "
            "Pass its path with --povray PATH (or povray=... when calling "
            "main), or set the POVRAY environment variable."
        )
    return resolved


def select_top_surface_oxygen(atoms):
    """Select O atoms in the upper surface/adsorbate region."""

    symbols = np.asarray(atoms.get_chemical_symbols())
    return (symbols == "O") & (atoms.positions[:, 2] > 24.0)


def main(
    *,
    render: bool = True,
    povray: str | Path | None = None,
    output: str | Path | None = None,
    quality: int = QUALITY,
) -> None:
    """Build the example and render it, or only write its POV-Ray scene."""

    output_path = Path(output) if output is not None else Path.cwd() / DEFAULT_OUTPUT
    executable = resolve_povray_executable(povray) if render else None
    structure = load_structure(INPUT)
    bond_rules = get_default_bonds(structure, profile=HEMATITE_SIDE_VIEW)
    geometry = build_geometry(
        structure,
        bond_rules=bond_rules,
        bounds=DisplayBounds(
            fractional_ranges=((0.0, 1.0), (0.0, 1.0), (0.5, 0.8))
        ),
    )
    style_config = StyleConfig(
        profile=HEMATITE_SIDE_VIEW,
        selection_rules=(
            AtomSelectionRule(
                selector=select_top_surface_oxygen,
                style=AtomStyleOverride(color=SURFACE_OXYGEN_COLOR),
            ),
        ),
    )
    styled = apply_styles(geometry, style_config)

    camera = Camera.orthographic(
        direction=(0.0, 100.0, -25.0),
        target=(7.6, 7.0, 25.0),
        profile=HEMATITE_SIDE_VIEW,
    )
    scene = make_scene(
        styled.primitives,
        camera=camera,
        lights=(get_side_view_light(camera),),
        profile=HEMATITE_SIDE_VIEW,
    )

    if render:
        assert executable is not None
        result = render_scene(
            scene,
            output_path,
            RenderConfig(
                profile=HEMATITE_SIDE_VIEW,
                quality=quality,
                executable=executable,
            ),
        )
        print(f"Rendered {result.image_path}")
    else:
        scene_path = output_path.with_suffix(".pov")
        scene_path.parent.mkdir(parents=True, exist_ok=True)
        write_scene(scene, scene_path, profile=HEMATITE_SIDE_VIEW)
        print(f"Wrote {scene_path}")


def build_parser() -> ArgumentParser:
    """Create the command-line parser for this example."""

    parser = ArgumentParser(description=__doc__)
    parser.add_argument(
        "--povray",
        metavar="PATH",
        help="POV-Ray executable; overrides the POVRAY environment variable",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path.cwd() / DEFAULT_OUTPUT,
        help=f"output image path (default: ./{DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--quality",
        type=int,
        default=QUALITY,
        help=f"POV-Ray render quality (default: {QUALITY}; use 3 for previews)",
    )
    parser.add_argument(
        "--no-render",
        action="store_true",
        help="write the .pov scene without invoking POV-Ray",
    )
    return parser


if __name__ == "__main__":
    argument_parser = build_parser()
    arguments = argument_parser.parse_args()
    try:
        main(
            render=not arguments.no_render,
            povray=arguments.povray,
            output=arguments.output,
            quality=arguments.quality,
        )
    except RuntimeError as error:
        argument_parser.error(str(error))
