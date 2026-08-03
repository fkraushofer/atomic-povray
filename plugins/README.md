# Optional plugins

This directory contains domain-specific helpers that integrate with
`atomic-povray` through its public primitive API. They intentionally remain
outside `src/atomic_povray` and are not installed as part of the core package.

## VASP isosurfaces

`vasp_isosurfaces.py` converts positive and negative charge-density surfaces
from a VASP volumetric file into `TriangleMeshPrimitive` objects. Its public
`level` argument uses the value shown by VESTA (electrons per bohr³), it treats
the grid as periodic by default, and it can persist the generated geometry in
a versioned `.npz` cache.

Install the additional mesh-extraction dependency:

```bash
python -m pip install scikit-image
```

Generate and cache the meshes once:

```python
from plugins.vasp_isosurfaces import create_vasp_isosurface_cache

positive, negative = create_vasp_isosurface_cache(
    "CHGDIFF",
    "CHGDIFF_0.001.npz",
    level=0.001,
)
```

Load the cached geometry later using the default yellow/cyan materials:

```python
from plugins.vasp_isosurfaces import load_isosurface_meshes

positive, negative = load_isosurface_meshes("CHGDIFF_0.001.npz")
```

Materials are not stored in the cache and can therefore be replaced without
recalculating the surfaces. See the module docstring and function docstrings
for the complete API.
