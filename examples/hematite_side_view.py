"""Reproduce the structural scope of the legacy hematite POV-Ray example."""

from pathlib import Path
from time import perf_counter

from atomic_povray import (
    AtomStyle,
    Background,
    BondRule,
    BondStyle,
    Camera,
    CartesianBounds,
    Color,
    PointLight,
    RenderConfig,
    StyleConfig,
    apply_styles,
    build_geometry,
    load_structure,
    make_scene,
    render_scene,
    write_scene,
)

ROOT = Path(__file__).resolve().parents[1]
INPUT = ROOT / "tests" / "data" / "hematite_1x1_unrelaxed_bare.vasp"
OUTPUT = ROOT / "hematite_prototype1.pov"


def main(*, render: bool = False) -> None:
    structure = load_structure(INPUT)

    start = perf_counter()
    geometry = build_geometry(
        structure,
        repetitions=(2, 1, 1),
        bounds=CartesianBounds(z_min=17.0),
        bond_rules=(BondRule("Fe", "O", 0.1, 2.45),),
    )
    geometry_seconds = perf_counter() - start

    styles = StyleConfig(
        elements={
            "Fe": AtomStyle(0.55, Color.from_hex("#A8463B")),
            "O": AtomStyle(0.34, Color.from_hex("#E6D44A")),
        },
        bonds={
            # No explicit color: each bond is split into Fe- and O-colored halves.
            "Fe-O": BondStyle(radius=0.074),
        },
    )
    styled = apply_styles(geometry, styles)
    camera = Camera.orthographic(
        location=(5.0, -100.0, 25.5),
        target=(5.0, 0.0, 25.5),
        up=(0.0, 0.0, 1.0),
        width=21.0,
    )
    scene = make_scene(
        styled.primitives,
        camera=camera,
        lights=(PointLight((15.0, -30.0, 55.0), intensity=1.15),),
        background=Background(Color(1.0, 1.0, 1.0)),
    )

    write_scene(scene, OUTPUT, width=1200, height=900)
    print(
        f"Geometry: {len(geometry.primary_atoms)} primary + "
        f"{len(geometry.extension_atoms)} bond-extension atoms, "
        f"{len(geometry.bonds)} bonds in {geometry_seconds:.3f} s"
    )
    print(f"Wrote {OUTPUT}")

    if render:
        result = render_scene(
            scene,
            ROOT / "hematite_prototype1.png",
            RenderConfig(width=1200, height=900, quality=3),
        )
        print(f"Rendered {result.image_path}")


if __name__ == "__main__":
    main()
