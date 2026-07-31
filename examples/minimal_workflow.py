"""Minimal end-to-end atomic-povray example.

This is the script counterpart of ``notebooks/prototype_workflow.ipynb``.
Set the POVRAY environment variable when the executable is not on PATH.
"""

from os import environ
from pathlib import Path

from atomic_povray import (
    Background,
    Camera,
    Color,
    DisplayBounds,
    RenderConfig,
    StyleConfig,
    apply_styles,
    build_geometry,
    get_default_bonds,
    get_default_light,
    load_structure,
    make_scene,
    render_scene,
)


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "tests" / "data" / "fe2o3-012-1x1-relaxed.vasp"
OUTPUT = ROOT / "hematite_minimal.png"


def main() -> None:
    structure = load_structure(INPUT)
    bond_rules = get_default_bonds(structure)
    geometry = build_geometry(
        structure,
        bond_rules=bond_rules,
        bounds=DisplayBounds(
            fractional_ranges=((-2.0, 2.0), (-1.5, 1.5), (0.45, 0.75))
        ),
    )
    styled = apply_styles(geometry, StyleConfig())

    camera = Camera.orthographic(
        direction=(0.0, 100.0, 0.0),
        target=(0.0, 0.0, 21.0),
        up=(0.0, 0.0, 1.0),
        width=21.0,
    )
    scene = make_scene(
        styled.primitives,
        camera=camera,
        lights=(get_default_light(camera),),
        background=Background(Color(1.0, 1.0, 1.0)),
    )
    result = render_scene(
        scene,
        OUTPUT,
        RenderConfig(
            width=1024,
            height=768,
            quality=5,
            executable=environ.get("POVRAY", "povray"),
        ),
    )
    print(f"Rendered {result.image_path}")


if __name__ == "__main__":
    main()
