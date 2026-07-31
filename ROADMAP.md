# Project roadmap

This roadmap replaces the original prototype outline. Items listed as complete are already part of the current foundation rather than future milestones.

## Current foundation

The initial structural and rendering pipeline is established:

- ASE-readable structure input; no custom `.povin` format
- floating-point fractional display ranges combining replication, offset, and crop
- Cartesian cutoff planes defined by normal and signed distance
- asymmetric, symmetric, or disabled one-hop bond extensions
- per-face and per-plane extension control
- periodic bond discovery for skewed cells
- atom spheres with ASE-backed fallback colors and covalent radii
- automatic editable default bond inference for conservative element pairs
- single- or two-color cylindrical bonds
- layered atom styling by coordination, ASE selection, source atom, or periodic
  display instance
- solid, dashed, and dotted bond styles with configurable segment counts and radii
- orthographic and perspective cameras
- point and area lights
- configurable background color and transparent output
- shared default finishes with atom- and bond-specific overrides
- directional exponential depth shading resolved per primitive
- native POV-Ray constant fog for continuous camera-distance fading
- POV-Ray 3.7 SDL and INI export, plus direct rendering
- generic extra-primitives insertion for future arrows, cells, isosurfaces, and similar objects
- compact 1×1 hematite notebook example and focused regression tests

A background color is set when constructing the scene, for example:

```python
scene = make_scene(
    styled.primitives,
    camera=camera,
    lights=lights,
    background=Background(Color.from_hex("#F2F2F2")),
)
```

Whether that background appears in the PNG still depends on `RenderConfig.transparent`. With transparency enabled, POV-Ray preserves alpha; disable it when an opaque background color is desired.

## Milestone 2: styling and annotations

The next milestone should complete the important appearance controls without changing structural geometry.

- Atom labels represented as text primitives
- Tests for depth mapping and labels

The atom-style resolution order should be:

```text
global defaults
→ element style
→ coordination rule
→ selection rule
→ individual atom override
```

“Special atoms” and coordination coloring should therefore share one rule-based mechanism rather than become separate hard-coded subsystems.

## Milestone 3: polyhedra, alternate atoms, and persistent geometry

- Coordination polyhedra constructed with SciPy
- Transparent polyhedron materials
- Robust face orientation and normals
- Handling of coplanar and nearly coplanar neighbor sets
- Persistent content-addressed geometry cache
- Stable export/import format for cached geometry
- Timing benchmarks and larger realistic regression tests

Cache keys should be based on contents and relevant configuration, not filenames or modification times. Camera, lighting, background, and render resolution must not invalidate geometry caches.

Prefer a stable representation such as compressed NumPy arrays plus JSON metadata over making pickle/joblib the long-term public interchange format.

## Milestone 4: interactive notebook frontend

- `ipywidgets` controls for camera, field of view, colors, lighting, and render settings
- Explicit low-quality preview and final-quality render actions
- Optional debounce after camera changes
- Reduced preview mode that may render atom spheres only at low quality
- Optional rasterized/OpenGL preview backend for fluid camera placement
- Final POV-Ray rendering on demand

Smooth full-scene POV-Ray updates are not a requirement. The practical target is fast camera placement followed by a complete final render. Any rasterized preview should consume the same styled primitives rather than duplicate structural logic.

## Later extensions

These are intentional extension points, not current core commitments:

- unit-cell outlines and vector arrows
- charge-density or other isosurfaces supplied by external modules
- additional rendering backends
- higher-level stateful viewer façade
- ViPErLEED integration

External scientific modules should calculate generic primitives and insert them during scene assembly. The core renderer need not understand the scientific meaning of those objects.
