# AGENTS.md

## Project purpose

`atomic-povray` converts ASE-readable atomic structures into reusable geometry, renderer-independent styled primitives, and POV-Ray scenes. Notebook, standalone-script, and batch workflows share the same public API. The architecture must also remain suitable for later ViPErLEED integration and for external modules that contribute objects such as arrows, unit-cell edges, or isosurfaces.

Read `README.md` for the current API and user-facing workflow before making changes.

## Start every task by orienting yourself

- Read `README.md`, `pyproject.toml`, and the relevant source and tests before
  proposing or making changes.
- Run `git status --short --branch` and preserve all pre-existing user changes.
- Inspect the configured remotes and current branch rather than assuming that
  the checkout is on `main` or that `main` is the correct base.
- When a task depends on current GitHub state, use `gh repo view`, `gh pr list`,
  and `gh pr view` to verify branches, pull requests, review comments, and base
  branches. Historical handover notes are context, not an authoritative record
  of current state.
- Work in the existing local clone and its configured Python environment. Do
  not create a replacement checkout unless isolation is actually needed.

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

A shared default finish applies to atoms, bonds, and polyhedra unless a more
specific finish or full material overrides it. Preserve the documented
finish/material precedence.

Depth shading belongs in the style-resolution stage. Keep it out of geometry
and do not replace it with an undocumented light-intensity adjustment.

## Current design constraints

- Preserve style-scale precedence: an explicit `StyleConfig.atom_size_scale`
  overrides everything; an explicitly supplied profile's `atom_size_scale`
  survives preset selection; and a preset scale applies when no profile or
  explicit scale is supplied. Apply the effective scale only after resolving
  element, coordination, selection, and individual-atom radii.
- Interactive controls should expose useful individual overrides without
  requiring users to reconstruct a complete render configuration. Use the
  existing `_make_control_specs` mechanism as the single place that collects
  control defaults and metadata.
- Orthographic and perspective cameras should switch smoothly in apparent
  scale. A perspective camera may derive its angle from width and camera
  distance, while an explicit angle remains authoritative.
- Multiple lights and per-light controls are valid. Area-light
  `angular_diameter` is a meaningful independent parameter, including for
  colocated lights with different apparent source sizes.
- Polyhedra may be generated during geometry construction while remaining
  globally hidden by default. A global `draw_polyhedra` style switch gates all
  polyhedron drawing; when enabled, individual `PolyhedronStyle` rules may
  still hide selected polyhedra.
- Square-planar polyhedra are effectively planes. Dimension-two polyhedron
  meshes require `two_sided_lighting`, serialized as POV-Ray
  `double_illuminate`. Preserve that regression behavior, and inspect the
  emitted `.pov` syntax and effective transparency values before changing it.

## POV-Ray behavior

POV-Ray 3.7 is the default SDL compatibility target and executable example. Keep `assumed_gamma 1.0` explicit in generated scenes. SDL version, display gamma, file gamma, transparency, antialiasing, and render quality are separate settings.

Both workflows must remain supported:

- direct rendering through `render_scene`;
- standalone `.pov` plus matching `.ini` export through `write_scene` and `write_ini`.

Opening only a `.pov` file does not reproduce INI render settings; examples should make this distinction clear.

## Tests and examples

Every geometry change needs focused identity/count tests, not only image comparisons. In particular, test non-orthogonal periodic cells, boundary crossings, deduplication, asymmetric extension direction, one-hop non-recursion, and per-boundary extension control where relevant.

Every styling or backend change should test resolved primitive properties or emitted SDL/INI. Use rendered-image regression tests only as an additional check when a stable POV-Ray environment is available.

Run the complete test suite before publishing a change:

```bash
python -m pytest
```

First inspect `pyproject.toml` and the repository documentation for the
canonical test, lint, formatting, and documentation commands. Install declared
development/test dependencies into the active project environment if they are
missing. Do not claim that tests passed unless the tested files match the
committed content.

At present, the repository configures pytest but has no canonical lint,
formatting, type-checking, generated-documentation, or CI command. Do not
invent or claim such checks. Re-inspect the repository because this may change.

If a dependency, external binary, or test fixture is genuinely unavailable,
run the strongest narrower checks and state the exact limitation in the final
report and PR description. POV-Ray itself is only required for tests that
actually invoke rendering; SDL/INI generation tests should remain runnable
without it.

For rendering changes, verify serialized POV-Ray output and, where feasible,
perform a small actual render or exercise an existing notebook/example
workflow. Do not assume that a surprising visual result is a serializer bug:
inspect the emitted `.pov` file and effective style values first.

Update the notebook, examples, and README when a public API or documented workflow changes.

## Development workflow

Keep feature requests in focused branches and pull requests. Use branch names beginning with `agent/` for agent-authored work and open draft PRs unless the user asks otherwise.

- Never discard, overwrite, stash, or fold unrelated uncommitted work into a
  task. If user changes overlap the requested edit, stop and clarify before
  risking them.
- Before creating a feature branch, fetch and verify the requested base branch
  and its relationship to the current checkout. This project has sometimes
  used version or feature branches instead of `main`.
- Preserve backward compatibility unless the task explicitly authorizes a
  breaking change.
- Prefer existing dataclasses, helpers, naming patterns, and control-generation
  machinery over parallel implementations.
- Before the first GitHub write in a session, verify the authenticated account
  and repository with `gh auth status` and `gh repo view`.
- When asked to publish, commit only the task-relevant changes, push the feature
  branch, and open a **draft** pull request with `gh`. Include a concise summary
  and the exact validation performed.
- Do not merge a pull request unless explicitly asked. Do not force-push,
  rewrite published history, or delete branches without explicit approval.

Keep diffs scoped. Do not modify unrelated files or overwrite user changes. Explain deliberate behavioral changes in the PR description.

Avoid speculative framework work. Implement the smallest complete layer needed for the current milestone while preserving the staged architecture and extension points above.

## Definition of done

- Relevant tests pass, or exact test limitations are documented.
- Public behavior, README text, examples, and notebooks remain consistent.
- The diff contains only task-relevant changes.
- Current GitHub state and the PR base were verified rather than assumed.
- The final report names changed files, validation performed, and any remaining
  uncertainty.
