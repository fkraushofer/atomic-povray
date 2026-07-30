# atomic-povray — Prototype 1

This package provides a pipeline to render atomic structures from the
Atomic Simulation Environment (ASE) in POV-Ray. It reads any
ASE-supported structure, constructs a finite replicated and cropped atomic
geometry once, resolves periodic bonds, converts that geometry to
renderer-independent primitives, and only then writes or renders a POV-Ray
scene.

Currently, the workflow is to generate a POV-Ray SDL input file, then execute
the POV-Ray engine as a subprocess with that input. Alternatively, the input
file can be written and then rendered manually.

## What is implemented

- ASE structure loading
- floating-point fractional ranges that combine replication, offset, and crop
- optional Cartesian cutoff planes defined by a normal and signed distance
- one-hop bond-extension atoms across clipping and replication boundaries
- asymmetric Fe→O-style boundary extension by default, with symmetric and
  disabled modes available per bond rule
- per-plane and per-fractional-face control over whether extensions are allowed
- element-pair bond rules with minimum and maximum distances
- periodic bond discovery, including skewed cells and bonds crossing cell edges
- stable atom identity as `(source_index, lattice_shift)`
- atom spheres
- single-color or two-color bonds (with the legacy equal-visible-length split)
- a shared default finish for atoms and bonds, with per-style material or finish
  overrides
- perspective and orthographic cameras
- point lights, backgrounds, transparent output
- direct POV-Ray SDL and INI generation
- an `extra_primitives=` scene hook for later unit cells, arrows, isosurfaces, etc.
- notebook-friendly, explicitly staged API

Coordination styles, dashed H-bonds, depth shading, labels, polyhedra,
persistent disk caching, and an interactive preview are intentionally deferred.

## Installation

Create a clean environment and install the project in editable mode:

```bash
conda create -n atomic-povray python=3.12 povray -c conda-forge
conda activate atomic-povray
python -m pip install -e ".[test,notebook]"
```

If POV-Ray is already installed separately on Windows, the Python package does
not need to install it. Point `RenderConfig.executable` at `pvengine64.exe`.

## Staged notebook API

```python
from atomic_povray import *

structure = load_structure("POSCAR")

# This is the expensive stage. Reuse `geometry` while changing appearance/camera.
geometry = build_geometry(
    structure,
    bounds=DisplayBounds(
        fractional_ranges=((-2.0, 2.0), (-1.5, 1.5), (0.45, 0.75)),
        cutoff_planes=(
            CutoffPlane(normal=(1.0, 0.0, 0.0), distance=9.5),
        ),
    ),
    # Order matters only for extensions: an in-bounds Fe may pull in an
    # out-of-bounds O, but an in-bounds O does not pull in an Fe.
    bond_rules=[BondRule("Fe", "O", 0.1, 2.45)],
)

styles = StyleConfig(
    elements={
        "Fe": AtomStyle(radius=0.55, color=Color.from_hex("#A63B32")),
        "O": AtomStyle(radius=0.34, color=Color.from_hex("#E6D84A")),
    },
    bonds={"Fe-O": BondStyle(radius=0.074)},
)
styled = apply_styles(geometry, styles)

camera = Camera.orthographic(
    direction=(0.0, 100.0, 0.0),
    target=(5.0, 0.0, 25.5),
    up=(0.0, 0.0, 1.0),
    width=21.0,
)
scene = make_scene(
    styled.primitives,
    camera=camera,
    lights=(PointLight(location=(20.0, -40.0, 60.0)),),
    background=Background(Color(1.0, 1.0, 1.0)),
)

write_scene(scene, "hematite.pov")
render_scene(scene, "hematite.png", RenderConfig(quality=3))
```

The camera `direction` points from the camera toward `target`; its magnitude
sets the camera distance. The emitted camera position is therefore
`target - direction`. Keeping `direction` fixed while changing `target`
translates the view without changing its orientation or perspective.

Changing the camera only repeats `make_scene` and `render_scene`. Changing
colors/radii repeats `apply_styles` onward. Neither operation repeats periodic
bond detection.

## Finishes and overrides

The built-in default finish is used for every atom and bond that does not
provide a more specific finish or material. Its values reproduce the common
legacy finish: ambient `0.10`, diffuse `0.60`, Phong `0.0`, and Phong size
`10`. No finish declaration is required for that behavior:

```python
styles = StyleConfig(
    elements={
        "Fe": AtomStyle(0.55, Color(0.10, 0.10, 1.10)),
        "O": AtomStyle(0.34, Color(1.05, 0.10, 0.05)),
    },
    bonds={"Fe-O": BondStyle(radius=0.074)},
)
```

To change the shared default, pass
`StyleConfig(default_finish=Finish(...), ...)`.
Override only the finish while retaining the atom or bond color with
`AtomStyle(..., finish=another_finish)` or
`BondStyle(..., finish=another_finish)`. Supplying `material=Material(...)`
overrides both color and finish. The resolution order is:

1. an explicit `material`;
2. an explicit `finish`, combined with the style color;
3. `StyleConfig.default_finish`, combined with the style color.

`BondStyle.material_template` remains available for compatibility with the
first prototype, but `finish=` is clearer for new code because a finish has no
dummy pigment color.

## Boundary and bond-extension behavior

`DisplayBounds` is the only boundary model. Its three fractional `(min, max)`
ranges correspond to the three unit-cell vectors and simultaneously define
replication, offset, and fractional cropping:

```python
bounds = DisplayBounds(
    fractional_ranges=((-2.0, 2.0), (-1.5, 1.5), (0.45, 0.75)),
)
```

Ranges are half-open: the lower endpoint is included and the upper endpoint is
excluded. Thus `(0.0, 3.0)` gives exactly three copies along that lattice
vector, while non-integer endpoints crop or offset the displayed region.

Optional Cartesian cutoff planes remove everything beyond their normal:

```python
bounds = DisplayBounds(
    fractional_ranges=((0.0, 3.0), (0.0, 2.0), (0.0, 1.0)),
    cutoff_planes=(
        CutoffPlane(normal=(1.0, 1.0, 0.0), distance=12.0),
    ),
)
```

The normal is normalized internally; `distance` is the signed perpendicular
distance from the Cartesian origin. A point is retained when
`unit(normal) · position <= distance`.

Every displayed atom is either a primary atom satisfying all fractional ranges
and cutoff planes, or a bond-extension atom outside at least one such boundary.
Extension atoms are admitted only as direct endpoints of bonds initiated from
primary atoms. They never initiate another neighbor search, so extensions
cannot grow recursively beyond the first outside atom.

The default bond rule is asymmetric and uses its declared element order:

```python
BondRule("Fe", "O", 0.1, 2.45)
```

This lets an in-bounds Fe pull in a bonded O outside the boundary, matching
VESTA's default behavior. It does not let an in-bounds O pull in an Fe. To
search in both directions, request it explicitly:

```python
BondRule("Fe", "O", 0.1, 2.45, extension_mode="symmetric")
```

Use `extension_mode="none"` to suppress extensions for that rule. Each cutoff
plane can independently forbid bond extensions across itself:

```python
bounds = DisplayBounds(
    cutoff_planes=(
        CutoffPlane(
            normal=(1.0, 0.0, 0.0),
            distance=12.0,
            allow_bond_extensions=False,
        ),
    )
)
```

The six fractional range faces follow the same default: extensions are allowed.
Their lower and upper faces can be configured separately:

```python
bounds = DisplayBounds(
    fractional_ranges=((0.0, 2.0), (0.0, 1.0), (0.0, 1.0)),
    lower_allow_bond_extensions=(True, True, True),
    upper_allow_bond_extensions=(False, True, True),
)
```

The example above disables extensions through the upper face normal to the
first lattice vector while retaining them at the other five faces.

The `notebooks/prototype_workflow.ipynb` notebook and
`examples/hematite_side_view.py` contain complete examples.

## Extra primitive hook

External modules can construct generic primitives and append them without the
core knowing their scientific meaning:

```python
cell_edge = CylinderPrimitive(
    start=(0, 0, 0),
    end=tuple(structure.cell[0]),
    radius=0.03,
    material=Material(Color(0.1, 0.1, 0.1)),
)

scene = make_scene(
    styled.primitives,
    camera=camera,
    extra_primitives=(cell_edge,),
)
```

`TriangleMeshPrimitive` is already part of the generic primitive model so a
later charge-density or convex-hull module can insert triangle meshes.

## Rendering

`write_scene` and `write_ini` only need Python. `render_scene` additionally
needs POV-Ray. It writes a `.pov` scene and `.ini` render file beside the
requested image.
Generated scenes explicitly include `global_settings { assumed_gamma 1.0 }`.
The generated SDL and `RenderConfig` default to POV-Ray 3.7. Use
`povray_version="3.8"` only when 3.8-specific SDL compatibility is needed.

To export both files for opening or rendering manually in POV-Ray:

```python
config = RenderConfig(width=1200, height=900, quality=5)
scene_path = write_scene(
    scene,
    "hematite.pov",
    width=config.width,
    height=config.height,
    povray_version=config.povray_version,
)
ini_path = write_ini(scene_path, "hematite.png", config)
```

Open or render `hematite.ini`, rather than the `.pov` file alone, to retain
the configured output gamma, antialiasing, transparency, quality, and size.

Linux/macOS command-line builds normally use:

```python
RenderConfig(executable="povray")
```

Windows installations commonly use:

```python
RenderConfig(executable=r"C:\Program Files\POV-Ray\v3.7\bin\pvengine64.exe")
```

The package detects `pvengine*.exe` and uses `/RENDER ... /EXIT`; other
executables are called with the generated INI filename.

## Tests

```bash
python -m pytest
```

The tests cover ordinary and boundary-crossing bonds, skewed cells, clipping
planes, asymmetric and symmetric one-hop extensions, non-recursion, per-plane
extension control, replication identities, bicolored styling, extra
primitives, shared and overridden finishes, gamma settings, and SDL output.
