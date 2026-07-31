"""Feature example: hydrated Rh/hematite with custom defaults.

Demonstrates automatically generated covalent and dashed hydrogen bonds,
selection-based surface-oxygen coloring, and reusable appearance settings.
"""

from os import environ
from pathlib import Path

import numpy as np

from atomic_povray import (
    AtomSelectionRule,
    AtomStyleOverride,
    Background,
    Camera,
    Color,
    DisplayBounds,
    RenderConfig,
    StyleConfig,
    apply_styles,
    build_geometry,
    get_default_bonds,
    load_structure,
    make_scene,
    render_scene,
)
from my_defaults import (
    AMBIENT_SCALE,
    SURFACE_OXYGEN_COLOR,
    atom_styles,
    legacy_light,
)


ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "tests" / "data" / "rh-h2o-hematite.vasp"
OUTPUT = ROOT / "rh_h2o_hematite.png"


def select_top_surface_oxygen(atoms):
    """Select O atoms in the upper surface/adsorbate region."""

    symbols = np.asarray(atoms.get_chemical_symbols())
    return (symbols == "O") & (atoms.positions[:, 2] > 24.0)


def main() -> None:
    structure = load_structure(INPUT)
    bond_rules = get_default_bonds(structure)
    geometry = build_geometry(
        structure,
        bond_rules=bond_rules,
        bounds=DisplayBounds(
            fractional_ranges=((0.0, 1.0), (0.0, 1.0), (0.5, 0.8))
        ),
    )
    styles = StyleConfig(
        atom_size_scale=1.0,
        elements=atom_styles(structure.atoms.get_chemical_symbols()),
        ambient_scale=AMBIENT_SCALE,
        selection_rules=(
            AtomSelectionRule(
                selector=select_top_surface_oxygen,
                style=AtomStyleOverride(color=SURFACE_OXYGEN_COLOR),
            ),
        ),
    )
    styled = apply_styles(geometry, styles)

    camera = Camera.orthographic(
        direction=(0.0, 100.0, -25.0),
        target=(7.6, 7.0, 25.0),
        up=(0.0, 0.0, 1.0),
        width=20.0,
    )
    scene = make_scene(
        styled.primitives,
        camera=camera,
        lights=(legacy_light(camera),),
        background=Background(Color(1.0, 1.0, 1.0)),
    )
    result = render_scene(
        scene,
        OUTPUT,
        RenderConfig(
            width=1200,
            height=900,
            quality=5,
            executable=environ.get("POVRAY", "povray"),
        ),
    )
    print(f"Rendered {result.image_path}")


if __name__ == "__main__":
    main()
