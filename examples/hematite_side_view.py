"""Render the hematite side-view example from the command line.

Run from the repository root:

    python -m examples.hematite_side_view

Generated files are written to the current working directory by default. Use
``--output`` to choose another location and ``--no-render`` to write only the
POV-Ray scene.
"""

from argparse import ArgumentParser
from os import environ
from pathlib import Path
from shutil import which
from time import perf_counter

from atomic_povray import (
    Background,
    Camera,
    Color,
    DepthShading,
    DisplayBounds,
    PointLight,
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

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "tests" / "data" / "fe2o3-012-1x1-relaxed.vasp"
DEFAULT_OUTPUT = "hematite_side_view.png"


def resolve_povray_executable(povray: str | Path | None = None) -> str:
    """Resolve an explicit path, ``POVRAY``, or ``povray`` on ``PATH``."""

    candidate = str(povray) if povray is not None else environ.get("POVRAY", "povray")
    resolved = which(candidate)
    if resolved is None:
        raise RuntimeError(
            f"Could not resolve the POV-Ray executable {candidate!r}. "
            "Pass its path with --povray PATH (or povray=... when calling "
            "main), or set the POVRAY environment variable. For example, "
            "POVRAY=povray on Linux/Conda or "
            r'POVRAY="C:\Program Files\POV-Ray\v3.7\bin\pvengine64.exe" '
            "on Windows."
        )
    return resolved


def main(
    *,
    render: bool = True,
    povray: str | Path | None = None,
    output: str | Path | None = None,
) -> None:
    """Build the example and render it, or only write its POV-Ray scene."""

    output_path = Path(output) if output is not None else Path.cwd() / DEFAULT_OUTPUT
    executable = resolve_povray_executable(povray) if render else None
    structure = load_structure(INPUT)
    bond_rules = get_default_bonds(structure)

    start = perf_counter()
    geometry = build_geometry(
        structure,
        bounds=DisplayBounds(
            fractional_ranges=((-2.0, 2.0), (-1.5, 1.5), (0.45, 0.75))
        ),
        bond_rules=bond_rules,
    )
    geometry_seconds = perf_counter() - start

    styles = StyleConfig(
        depth_shading=DepthShading(
            origin=(0.0, 0.0, 24.0),
            direction=(0.0, 0.0, -1.0),
            decay_length=30.0,
            target=Color(1.0, 1.0, 1.0),
        ),
    )
    styled = apply_styles(geometry, styles)
    camera = Camera.orthographic(
        direction=(0.0, 100.0, 0.0),
        target=(0.0, 0.0, 21.0),
        up=(0.0, 0.0, 1.0),
        width=21.0,
    )
    scene = make_scene(
        styled.primitives,
        camera=camera,
        lights=(PointLight((15.0, -30.0, 55.0), intensity=1.15),),
        background=Background(Color(1.0, 1.0, 1.0)),
    )

    print(
        f"Geometry: {len(geometry.primary_atoms)} primary + "
        f"{len(geometry.extension_atoms)} bond-extension atoms, "
        f"{len(geometry.bonds)} bonds in {geometry_seconds:.3f} s"
    )

    if render:
        assert executable is not None
        result = render_scene(
            scene,
            output_path,
            RenderConfig(
                width=1200,
                height=900,
                quality=3,
                executable=executable,
            ),
        )
        print(f"Rendered {result.image_path}")
    else:
        scene_path = output_path.with_suffix(".pov")
        scene_path.parent.mkdir(parents=True, exist_ok=True)
        write_scene(scene, scene_path, width=1200, height=900)
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
        )
    except RuntimeError as error:
        argument_parser.error(str(error))
