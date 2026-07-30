# AGENTS.md

## Project purpose

`atomic-povray` converts ASE-readable atomic structures into reusable geometry, renderer-independent styled primitives, and POV-Ray scenes. The notebook API is the first frontend. The architecture must also remain suitable for later ViPErLEED integration and for external modules that contribute objects such as arrows, unit-cell edges, or isosurfaces.

Read `README.md` for the current API and `ROADMAP.md` for planned milestones before making changes.

## Architectural boundaries

Keep the staged pipeline explicit:

1. ASE structure input
2. immutable geometry construction
3. rule-based styling into generic primitives
4. scene assembly
5. POV-Ray SDL/INI generation and rendering

Expensive structural operations belong in the geometry stage. Camera, lighting, background, image size, and render-quality changes must not rebuild geometry.

Keep structural atoms and bonds free of colors, finishes, and renderer methods. Styling resolves structural objects into generic primitives such as spheres, cylinders, meshes, and text. The POV-Ray backend consumes those primitives; it must not perform chemical neighbour searches or coordination analysis.

Compose with `ase.Atoms`; do not subclass it. ASE-readable files are the input interface. Do not restore the legacy `.povin` format.

Keep backend-independent models serializable and testable. Direct POV-Ray SDL generation is the primary backend. Do not make `fdray` or another rendering wrapper foundational.

Preserve `extra_primitives` as the extension point for externally generated scene content. Domain-specific isosurface, arrow, or unit-cell calculations do not belong in the core package unless deliberately adopted later.

## Geometry invariants

`DisplayBounds` is the sole boundary model.

- Its three fractional ranges combine replication, offset, and cropping.
- Ranges are half-open: lower endpoints are included and upper endpoints excluded.
- Optional Cartesian cutoff planes use a normal and signed perpendicular distance from the origin.
- Fractional faces and cutoff planes follow the same clipping and extension rules.
- Each face or plane may independently disable bond extensions.
- Atom identity is stable as `(source_index, lattice_shift)`.

Bond rules are directional for boundary extension. For `BondRule("Fe", "O", ...)`, an in-bounds Fe may pull in an outside O by default, but an in-bounds O does not pull in an outside Fe. Symmetric and disabled extension modes must remain explicit options.

Extension atoms are strictly one hop deep. They may terminate bonds but must never initiate another search.

Periodic discovery must remain correct for skewed cells, bonds crossing multiple cell faces, reversed heteroatomic rule order, and homoatomic deduplication.

## Styling rules

Use a resolver rather than embedding appearance in structural objects. The intended precedence for atom appearance is:

1. global defaults
2. element style
3. coordination-dependent rule
4. selection rule
5. individual-atom override

Bond style belongs to the bond rule or its resolved style and should support a general style property, not a hydrogen-bond-specific special case. Solid, dashed, or future styles should produce ordinary primitives.

A shared default finish applies to atoms and bonds unless a more specific finish or full material overrides it. Preserve the documented finish/material precedence.

Depth shading is deferred styling work. Implement it in the style-resolution stage, not in geometry or as an undocumented light-intensity adjustment.

## Compatibility policy

This is still an early prototype. Prefer a clean, coherent API over backward-compatibility shims. When replacing an experimental API, remove the obsolete implementation, exports, tests, examples, and documentation in the same change. Do not leave deprecated zombie functions unless the user explicitly requests a compatibility period.

## POV-Ray behavior

POV-Ray 3.7 is the default SDL compatibility target and executable example. Keep `assumed_gamma 1.0` explicit in generated scenes. SDL version, display gamma, file gamma, transparency, antialiasing, and render quality are separate settings.

Both workflows must remain supported:

- direct rendering through `render_scene`;
- standalone `.pov` plus matching `.ini` export through `write_scene` and `write_ini`.

Opening only a `.pov` file does not reproduce INI render settings; examples should make this distinction clear.

## Tests and examples

Every geometry change needs focused identity/count tests, not only image comparisons. In particular, test non-orthogonal periodic cells, boundary crossings, deduplication, asymmetric extension direction, one-hop non-recursion, and per-boundary extension control where relevant.

Every styling or backend change should test resolved primitive properties or emitted SDL/INI. Use rendered-image regression tests only as an additional check when a stable POV-Ray environment is available.

Use `tests/data/fe2o3-012-1x1-relaxed.vasp` as the main compact realistic example. The 3×3 structure is a larger regression/performance case.

Run the complete test suite before publishing a change:

```bash
python -m pytest
```

Update the notebook, examples, README, and roadmap when a public API or milestone changes.

## Development workflow

Keep feature requests in focused branches and pull requests. Use branch names beginning with `agent/` for agent-authored work and open draft PRs unless the user asks otherwise.

When no suitable local checkout or authenticated `gh` CLI is available, use
the connected GitHub app directly for repository reads, branch creation,
file commits, and draft PR creation when those operations are exposed. Do not
treat a missing local `gh` installation as a blocker when the connector fully
covers the requested workflow; reserve `gh` for operations the connector
cannot perform, such as detailed Actions log inspection.

Keep diffs scoped. Do not modify unrelated files or overwrite user changes. Explain deliberate behavioral changes in the PR description.

Avoid speculative framework work. Implement the smallest complete layer needed for the current milestone while preserving the staged architecture and extension points above.
