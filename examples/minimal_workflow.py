"""Minimal end-to-end atomic-povray example.

This is the script counterpart of ``notebooks/prototype_workflow.ipynb``.
Run it from the repository root with:

    python -m examples.minimal_workflow

POV-Ray is found through the ``POVRAY`` environment variable or on ``PATH``.
If neither works, uncomment and adapt one of the example paths below.
"""

from os import environ
from pathlib import Path
from shutil import which

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
OUTPUT = Path.cwd() / "hematite_minimal.png"
QUALITY = 5  # Use 3 for a quick preview.

# Set the POVRAY environment variable to avoid keeping a machine-specific path
# in this script, or uncomment and adapt the appropriate line:
# POVRAY = r"C:\Program Files\POV-Ray\v3.7\bin\pvengine64.exe"  # Windows
# POVRAY = "/usr/bin/povray"  # Linux (often simply "povray" on PATH)
POVRAY = environ.get("POVRAY", "povray")


def main() -> None:
    povray_executable = which(POVRAY)
    if povray_executable is None:
        print(
            f"Could not resolve the POV-Ray executable {POVRAY!r}; "
            "skipping the render. Set the POVRAY environment variable to its "
            "full path, or edit POVRAY near the top of this script."
        )
        return

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
            quality=QUALITY,
            executable=povray_executable,
        ),
    )
    print(f"Rendered {result.image_path}")


if __name__ == "__main__":
    main()
