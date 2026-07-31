"""Reproduce the structural scope of the legacy hematite POV-Ray example."""

from pathlib import Path
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
OUTPUT = ROOT / "hematite_prototype1.pov"


def main(*, render: bool = False) -> None:
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
