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
- element-pair bond rules with half-open minimum/maximum distance ranges
- periodic bond discovery, including skewed cells and bonds crossing cell edges
- stable atom identity as `(source_index, lattice_shift)`
- atom spheres with ASE-backed fallback colors and covalent radii
- automatic, editable default bond rules for chemically plausible element pairs
- layered atom-style overrides by coordination, ASE selection, source index, or
  displayed periodic instance
- solid or dashed bonds, with configurable dash count and radius
- single-color or two-color bonds (with the legacy equal-visible-length split)
- distinct default atom and bond finishes, with per-style material or finish
  overrides
- directional exponential depth shading with a configurable onset, direction,
  decay length, and target color
- native POV-Ray constant fog for continuous camera-distance fading
- perspective and orthographic cameras
- point lights, backgrounds, transparent output
- direct POV-Ray SDL and INI generation
- an `extra_primitives=` scene hook for later unit cells, arrows, isosurfaces, etc.
- optional per-vertex normals for smooth externally generated triangle meshes
- notebook-friendly, explicitly staged API

Labels, polyhedra, persistent disk caching, and an interactive preview are
intentionally deferred.

## Installation

Create a clean environment and install the project in editable mode:

```bash
conda create -n atomic-povray python=3.12 povray -c conda-forge
conda activate atomic-povray
python -m pip install -e ".[test,notebook]"
```

The `povray` Conda package puts the executable on the active environment's
`PATH`. A separate system installation works equally well.

## Configure the POV-Ray executable

Pass the command or full executable path to `RenderConfig.executable`. On
Linux, and with the Conda package on any platform, the executable is normally:

```python
config = RenderConfig(executable="povray")
```

A typical standalone Windows installation uses one of these paths:

```python
config = RenderConfig(
    executable=r"C:\\Program Files\\POV-Ray\\v3.7\\bin\\pvengine64.exe"
)
# POV-Ray 3.8 commonly installs under:
# r"C:\\Program Files\\POV-Ray\\v3.8\\bin\\pvengine64.exe"
```

The exact version directory depends on the installed release. The examples also
accept a `POVRAY` environment variable, which keeps machine-specific paths out
of scripts and notebooks:

```python
import os

config = RenderConfig(executable=os.environ.get("POVRAY", "povray"))
```

## Examples

| Example | Purpose |
| --- | --- |
| `notebooks/prototype_workflow.ipynb` | Minimal notebook workflow with inline image display |
| `examples/minimal_workflow.py` | The same minimal workflow as a regular Python script, with automatic executable lookup |
| `examples/hematite_side_view.py` | Command-line rendering, executable resolution, and staged geometry timing |
| `examples/rh_h2o_hematite.py` | Command-line hydrogen-bond and surface-color example with imported project defaults |
| `examples/my_defaults.py` | Reusable legacy atom colors, radii, finish, ambient scale, and area light |

Run the executable examples as modules from the repository root:

```bash
python -m examples.minimal_workflow
python -m examples.hematite_side_view
python -m examples.rh_h2o_hematite
```

The minimal script deliberately has no argument parser. It resolves POV-Ray
from the `POVRAY` environment variable or searches for `povray` on `PATH`;
if neither succeeds, it skips rendering and prints how to configure the path.
Commented Windows and Linux path examples near the top of the script can also
be adapted directly.

The side-view and Rh/H₂O examples render by default. Pass `--no-render` to
write only the POV-Ray scene, `--povray PATH` to select the executable, or
`--output PATH` to choose the image location. Without `--povray`, they check
the `POVRAY` environment variable and then search for `povray` on `PATH`.
Inputs are located relative to the repository, while generated files default
to the shell's current working directory.

The Rh/H₂O example intentionally keeps reusable appearance choices separate
from scene construction. Copy `my_defaults.py` into a project and adapt it when
several figures should share the same atom palette, sizes, finish, and lighting.

## Staged notebook API

```python
from atomic_povray import *

structure = load_structure("POSCAR")
bond_rules = get_default_bonds(structure)  # Prints the generated rule table.

# Edit bond_rules here before the expensive geometry stage, if needed.
geometry = build_geometry(
    structure,
    bond_rules=bond_rules,
    bounds=DisplayBounds(
        fractional_ranges=((-2.0, 2.0), (-1.5, 1.5), (0.45, 0.75)),
        cutoff_planes=(
            CutoffPlane(normal=(1.0, 0.0, 0.0), distance=9.5),
        ),
    ),
)

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
    target=(5.0, 0.0, 25.5),
    up=(0.0, 0.0, 1.0),
    width=21.0,
)
scene = make_scene(
    styled.primitives,
    camera=camera,
    lights=(get_default_light(camera),),
    background=Background(Color(1.0, 1.0, 1.0)),
)

write_scene(scene, "hematite.pov")
render_scene(scene, "hematite.png", RenderConfig(quality=3))
```

The camera `direction` points from the camera toward `target`; its magnitude
sets the camera distance. The emitted camera position is therefore
`target - direction`. Keeping `direction` fixed while changing `target`
translates the view without changing its orientation or perspective.

`get_default_light(camera)` creates a soft area light that tracks the camera,
offset half a camera distance upward and half a camera distance to screen-right.
This gives the target consistent elevated three-quarter illumination while the
view changes. Its defaults are equivalent to
`AreaLight(intensity=1.8, angular_diameter=35.0, samples=(9, 9), adaptive=3)`;
all four settings can be overridden directly.

Changing the camera only repeats `make_scene` and `render_scene`. Changing
colors/radii repeats `apply_styles` onward. Neither operation repeats periodic
bond detection.

## Atomic and bond defaults

Atom colors and radii fall back field by field to ASE's Jmol colors and
covalent radii. Explicit element styles therefore only need to contain the
properties that differ:

```python
styles = StyleConfig(
    elements={
        "Fe": AtomStyle(color=Color.from_hex("#A63B32")),
        "O": AtomStyle(radius=0.4),
    },
)
```

The default preset is a ball-and-stick representation: all resolved atom radii
are multiplied by `0.4`, bonds are drawn, and the default ordinary bond radius
is `0.08` Å. The atom scale is global and is applied after element,
coordination, selection, and individual-atom radius overrides.

Use the built-in presets directly when switching representations:

```python
ball_and_stick = StyleConfig(preset_style="ball_and_stick")
space_filling = StyleConfig(preset_style="space_filling")
```

`space_filling` uses an atom scale of `1.0` and omits bond primitives. Bond
geometry is retained, so coordination-dependent styles remain available and
switching presets does not require rebuilding geometry. Override the global atom and bond scales independently when needed. Both are
applied after resolving default or explicit per-style radii. The ambient
coefficient can likewise be scaled globally after resolving every atom and
bond material:

```python
styles = StyleConfig(
    atom_size_scale=0.55,
    bond_size_scale=1.25,
    ambient_scale=0.8,
)
```

Unlike the size scales, `ambient_scale=0.0` is valid and disables ambient
lighting for all styled atoms and bonds.

Generate bond rules explicitly before geometry construction. This makes the
exact rule set inspectable and editable; `build_geometry()` never adds hidden
rules. Pass an empty iterable to request an atom-only geometry intentionally
and without a warning:

```python
bond_rules = get_default_bonds(structure)
geometry = build_geometry(structure, bond_rules=bond_rules)
geometry_without_bonds = build_geometry(structure, bond_rules=())
```

If `bond_rules` is omitted, `build_geometry()` also produces atom-only
geometry, but warns that default rules may have been forgotten. It never
generates or adds bond rules implicitly.

To inspect, edit, or delete the defaults before geometry construction, materialize
an ordinary editable `BondRuleSet`. The call prints a table containing each
rule name, element pair, half-open distance range, and boundary-extension
direction:

```python
# Cell 1: load the structure and inspect the generated defaults.
structure = load_structure("POSCAR")
bond_rules = get_default_bonds(structure, bond_scale=1.2)
```

For a metal-metal bond such as Pt-Pt, add an explicit rule in the next cell
because metal-metal pairs are deliberately excluded from the chemical defaults:

```python
# Cell 2: make any project-specific changes before geometry is built.
bond_rules.remove("default:Fe-H")
bond_rules.update("default:Fe-O", max_distance=2.45)
bond_rules.remove_pair("H", "H")
bond_rules.add(
    BondRule(
        "Pt",
        "Pt",
        0.0,
        3.1,
        name="custom:Pt-Pt",
        extension_mode="symmetric",
    )
)
bond_rules.print_table()  # Optional: inspect the modified rules.

# Cell 3: this is the expensive stage.
geometry = build_geometry(structure, bond_rules=bond_rules)
```

The 3.1 Å Pt-Pt cutoff is only an example; choose it from the relevant
nearest-neighbor distances in the structure. Pass `print_table=False` to
`get_default_bonds` when the summary is not wanted.

Ordinary cutoffs are `bond_scale` times the sum of the two ASE covalent
radii. Heteronuclear metal/non-metal rules are oriented from metal to
non-metal, so the default asymmetric boundary extension completes
coordination shells around in-bounds metals. Homonuclear rules may also extend
past boundaries.

When O and H are both present, the returned set contains adjacent covalent O-H
and hydrogen O···H ranges. The hydrogen-bond maximum is fixed at 2.1 Å,
independent of `bond_scale`, uses `extension_mode="none"`, and receives a
dashed default style. It remains an ordinary rule and can be changed
separately:

```python
bond_rules.update("default:hydrogen:O-H", max_distance=2.3)
```

Use `include_pairs={("Fe", "Fe")}` to admit a pair excluded by the default
chemical policy, or `exclude_pairs={("Fe", "H")}` to suppress an otherwise
eligible pair.

The element data are read from ASE rather than copied from VESTA. ASE's
covalent radii are based on Cordero *et al.*, “Covalent radii revisited”
([DOI: 10.1039/B801115J](https://doi.org/10.1039/B801115J)); colors use ASE's
Jmol color table. VESTA inspired the conservative candidate-pair policy and
editable workflow, but no VESTA data files are redistributed.

## Atom style rules

Atom appearance resolves from the general element style through increasingly
specific partial overrides:

```text
global default
→ element style
→ coordination rules
→ selection rules
→ source-atom override
→ displayed-instance override
```

Selection rules receive the original ASE `Atoms` and may return one index, a
one-dimensional integer sequence, or a Boolean mask. The selector is evaluated
once per styling call and applies to every displayed image of each selected
source atom:

```python
styles = StyleConfig(
    elements={"O": AtomStyle(0.34, oxygen_color)},
    selection_rules=(
        AtomSelectionRule(
            selector=lambda atoms: (
                (np.asarray(atoms.get_chemical_symbols()) == "O")
                & (atoms.positions[:, 2] > 26.0)
            ),
            style=AtomStyleOverride(color=surface_oxygen_color),
        ),
    ),
)
```

Coordination is calculated during geometry construction from the complete
periodic bond-rule environment, before display clipping. A boundary atom
therefore does not appear undercoordinated merely because one of its neighbors
is outside the rendered region:

```python
styles = StyleConfig(
    ...,
    coordination_rules=(
        CoordinationStyleRule(
            element="Fe",
            coordination=4,
            neighbor_elements={"O"},
            bond_rules={"Fe-O"},
            style=AtomStyleOverride(color=tetrahedral_fe_color),
        ),
        CoordinationStyleRule(
            element="Fe",
            coordination=6,
            neighbor_elements={"O"},
            bond_rules={"Fe-O"},
            style=AtomStyleOverride(color=octahedral_fe_color),
        ),
    ),
)
```

Use `source_atom_overrides={17: ...}` for ASE atom 17 in every displayed
replication, or `atom_instance_overrides={AtomKey(17, (1, 0, 0)): ...}` for
one particular periodic image. Later matching rules win within a category, and
partial overrides retain properties they do not specify. Setting
`visible=False` also removes bonds incident to that atom. Split-color solid
and dashed bonds automatically use the final resolved endpoint colors.

## Bond styles and distance ranges

Bond-rule distance ranges are half-open: the minimum is included and the
maximum is excluded. Adjacent rules can therefore share a cutoff without
claiming the same bond. Give them distinct names so each rule can resolve to
its own style:

```python
geometry = build_geometry(
    structure,
    bond_rules=(
        BondRule("O", "H", 0.1, 1.2, name="covalent-O-H"),
        BondRule("O", "H", 1.2, 2.0, name="hydrogen-O-H"),
    ),
)

styles = StyleConfig(
    ...,
    bonds={
        "covalent-O-H": BondStyle(radius=0.07),
        "hydrogen-O-H": BondStyle(
            style="dashed",
            dashes=4,
            radius=0.05,
            color=Color(0.7, 0.7, 0.7),
        ),
    },
)
```

Dashed bonds divide the visible span between the atom surfaces into the
requested number of equal dashes with equal-sized gaps. An explicit bond
`color` or full `material` makes the complete bond single-color. When no color is
supplied,
solid and dashed bonds retain the default split based on their atom colors.

## Finishes and overrides

Atoms and bonds have distinct built-in finishes. Both use ambient `0.10`,
diffuse `0.60`, and Phong size `10`; atoms use Phong `0.30`, while bonds use
Phong `0.0`. Together with the automatic ASE colors/radii and the default bond
radius of `0.08` Å, no appearance declaration is required:

```python
styles = StyleConfig()
```

Override them independently with `default_atom_finish=` or
`default_bond_finish=`. The compatibility argument `default_finish=` still sets
a shared finish for both. Use `ambient_scale=` to multiply the ambient
coefficient of every resolved atom and bond material, including explicit
`Finish` and `Material` overrides:

```python
styles = StyleConfig(ambient_scale=0.5)
```

The scene-level `ambient_light` is a separate RGB multiplier in POV-Ray and
defaults to white. In normal use, leave it at that default and control overall
ambient strength with `StyleConfig.ambient_scale`; setting both to `0.5`
would multiply the ambient contribution twice.

Override only the finish while retaining the atom or bond color with
`AtomStyle(..., finish=another_finish)` or
`BondStyle(..., finish=another_finish)`. Supplying `material=Material(...)`
overrides both color and finish. The resolution order is:

1. an explicit `material`;
2. an explicit `finish`, combined with the style color;
3. the corresponding atom or bond default finish, combined with the style color.

`BondStyle.material_template` remains available for compatibility with the
first prototype, but `finish=` is clearer for new code because a finish has no
dummy pigment color.

## Depth shading and fog

Directional depth shading is resolved into primitive colors during
`apply_styles`:

```python
styles = StyleConfig(
    ...,
    depth_shading=DepthShading(
        origin=(0.0, 0.0, 24.0),
        direction=(0.0, 0.0, -1.0),
        decay_length=30.0,
        target=Color(1.0, 1.0, 1.0),
    ),
)
```

The origin defines the onset plane perpendicular to `direction`. Colors before
that plane are unchanged. Beyond it, the original color contribution decays
exponentially and is `1/e` after `decay_length`. Spheres use their centers,
cylinders their midpoints, and meshes the mean of their vertices. To reproduce
the fog-like appearance of the legacy renderer, diffuse and Phong lighting decay
as the square of the color factor, specular highlights decay as its cube, and
ambient lighting rises toward `1` so distant primitives flatten into the target
color. Alpha is preserved by default.

Set `shade_alpha=True` to blend opacity toward `target.alpha` as well:

```python
DepthShading(
    ...,
    target=Color(1.0, 1.0, 1.0, alpha=0.0),
    shade_alpha=True,
)
```

POV-Ray's native constant fog is available as a continuous alternative when
depth follows the camera view:

```python
scene = make_scene(
    styled.primitives,
    camera=camera,
    background=Background(Color.from_hex("#F2F2F2")),
    fog=Fog(
        distance=30.0,
        color=Color.from_hex("#F2F2F2"),
    ),
)
```

Native fog blends every pixel according to the distance traveled from the
camera, so it varies continuously across primitives. It has no independent
Cartesian onset or shading direction; use directional depth shading when those
controls matter. Matching the fog and background colors gives the usual
atmospheric fade.

POV-Ray evaluates fog only at render quality 9 or higher. The default
`RenderConfig(quality=3)` is deliberately retained because it is useful for
fast camera and lighting previews, but those previews omit fog. `render_scene`
emits a warning when a foggy scene is rendered below quality 9. Use
`RenderConfig(quality=9)` or higher for a final render that includes fog.

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

The minimal notebook and script provide the shortest complete path through the
pipeline. See the examples table above for feature-focused alternatives.

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

`TriangleMeshPrimitive` is part of the generic primitive model so external
charge-density or convex-hull modules can insert triangle meshes. Set its
optional `normals` field to one normal per vertex for smooth POV-Ray
`mesh2` shading; when normals are omitted, the existing faceted output is
preserved.

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

See [Configure the POV-Ray executable](#configure-the-pov-ray-executable) for
Linux, Conda, and Windows examples. The package detects `pvengine*.exe` and
uses `/RENDER ... /EXIT`; other executables are called with the generated INI
filename.

## Tests

```bash
python -m pytest
```

The tests cover ordinary and boundary-crossing bonds, skewed cells, clipping
planes, asymmetric and symmetric one-hop extensions, non-recursion, per-plane
extension control, replication identities, bicolored styling, extra
primitives, shared and overridden finishes, gamma settings, and SDL output.
