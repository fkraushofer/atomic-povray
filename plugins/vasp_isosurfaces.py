"""Convert VASP charge-density grids to atomic-povray triangle meshes.

This module deliberately lives outside :mod:`atomic_povray`: reading a VASP
volumetric file and extracting scientific isosurfaces are separate concerns
from rendering generic primitives.

Dependencies
------------
``numpy``, ``ase``, ``scikit-image``, and ``atomic-povray``.

Example
-------
Generate and cache geometry once:

>>> positive, negative = create_vasp_isosurface_cache(
...     "CHGDIFF",
...     "CHGDIFF_vesta_0.001.npz",
...     level=0.001,
... )

Load it later with independently configurable materials:

>>> positive, negative = load_isosurface_meshes(
...     "CHGDIFF_vesta_0.001.npz",
...     positive_material=my_yellow,
...     negative_material=my_cyan,
... )
>>> scene = make_scene(
...     styled.primitives,
...     camera=camera,
...     extra_primitives=(positive, negative),
... )
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from os import PathLike
from pathlib import Path
from typing import TYPE_CHECKING, Literal, overload

import numpy as np
from ase.calculators.vasp import VaspChargeDensity
from skimage.measure import marching_cubes

from atomic_povray import Color, Material, TriangleMeshPrimitive

if TYPE_CHECKING:
    from numpy.typing import ArrayLike, NDArray


DEFAULT_POSITIVE_MATERIAL = Material(
    Color(1, 1, 0, transmit=0.3, filter=0.1)
)
DEFAULT_NEGATIVE_MATERIAL = Material(
    Color(0, 1, 1, transmit=0.3, filter=0.1)
)

_CACHE_FORMAT = "atomic-povray-vasp-isosurfaces"
_CACHE_VERSION = 2

# VESTA displays VASP volumetric-density levels in electrons per bohr^3,
# whereas ASE's VaspChargeDensity returns electrons per angstrom^3.
BOHR_IN_ANGSTROM = 0.529177210903
VESTA_TO_ASE_DENSITY = 1.0 / BOHR_IN_ANGSTROM**3


@dataclass(frozen=True)
class IsosurfaceCacheMetadata:
    """Metadata stored alongside cached isosurface geometry."""

    format_version: int
    cell: tuple[tuple[float, float, float], ...] | None = None
    level: float | None = None
    level_ase: float | None = None
    level_units: str | None = None
    periodic: bool | None = None
    step_size: int | None = None
    source_name: str | None = None
    source_sha256: str | None = None


def vasp_isosurface_primitives(
    filename: str | PathLike[str],
    *,
    level: float,
    positive_material: Material = DEFAULT_POSITIVE_MATERIAL,
    negative_material: Material = DEFAULT_NEGATIVE_MATERIAL,
    periodic: bool = True,
    step_size: int = 1,
    allow_degenerate: bool = False,
) -> tuple[TriangleMeshPrimitive, TriangleMeshPrimitive]:
    """Read a VASP density file and return positive and negative isosurfaces.

    The returned order is ``(positive, negative)``. VASP grid samples occur at
    fractional coordinates ``i / n``. With the default ``periodic=True``, the
    first plane is appended at fractional coordinate 1 along every direction,
    so marching cubes also processes each interval crossing a cell boundary.

    Parameters
    ----------
    filename
        CHG, CHGCAR, CHGDIFF, or another VASP charge-density-format file.
    level
        Positive isodensity magnitude in VESTA units (electrons per bohr³).
        For example, ``level=0.001`` produces the same physical isosurface as
        level 0.001 in VESTA's isosurface dialog.
    positive_material, negative_material
        Materials for the ``+level`` and ``-level`` meshes.
    periodic
        Join the final grid interval back to the first in all three directions.
    step_size
        Marching-cubes step size. Use 1 for final output and 2 or 3 for preview.
    allow_degenerate
        Forwarded to :func:`skimage.measure.marching_cubes`.

    Raises
    ------
    ValueError
        If ``level`` is invalid, either signed surface is absent, or the VASP
        file does not contain a usable three-dimensional charge grid.
    """

    density, cell = _read_vasp_density(filename)
    return density_isosurface_primitives(
        density,
        cell,
        level=level,
        positive_material=positive_material,
        negative_material=negative_material,
        periodic=periodic,
        step_size=step_size,
        allow_degenerate=allow_degenerate,
    )


def density_isosurface_primitives(
    density: ArrayLike,
    cell: ArrayLike,
    *,
    level: float,
    positive_material: Material = DEFAULT_POSITIVE_MATERIAL,
    negative_material: Material = DEFAULT_NEGATIVE_MATERIAL,
    periodic: bool = True,
    step_size: int = 1,
    allow_degenerate: bool = False,
) -> tuple[TriangleMeshPrimitive, TriangleMeshPrimitive]:
    """Convert an ASE/VASP density grid using a VESTA-style isosurface level.

    ``density`` is expected in ASE's native electrons-per-ångström³ units,
    while ``level`` is interpreted in VESTA's electrons-per-bohr³ units.
    """

    level_ase = vesta_level_to_ase(level)

    density_array, cell_array = _validate_inputs(
        density,
        cell,
        level=level_ase,
        step_size=step_size,
    )
    positive = _isosurface_primitive(
        density_array,
        cell_array,
        level=level_ase,
        material=positive_material,
        label="positive",
        periodic=periodic,
        step_size=step_size,
        allow_degenerate=allow_degenerate,
    )
    negative = _isosurface_primitive(
        -density_array,
        cell_array,
        level=level_ase,
        material=negative_material,
        label="negative",
        periodic=periodic,
        step_size=step_size,
        allow_degenerate=allow_degenerate,
    )
    return positive, negative


def create_vasp_isosurface_cache(
    source_filename: str | PathLike[str],
    cache_filename: str | PathLike[str],
    *,
    level: float,
    positive_material: Material = DEFAULT_POSITIVE_MATERIAL,
    negative_material: Material = DEFAULT_NEGATIVE_MATERIAL,
    periodic: bool = True,
    step_size: int = 1,
    allow_degenerate: bool = False,
    compressed: bool = True,
    geometry_dtype: np.dtype | type = np.float32,
    include_source_hash: bool = True,
) -> tuple[TriangleMeshPrimitive, TriangleMeshPrimitive]:
    """Generate meshes from a VASP file and immediately cache their geometry.

    This convenience function records the cell, VESTA and ASE isovalues,
    step size, source basename, and (by default) a SHA-256 source digest.
    It returns the generated primitives so they can also be rendered directly.
    """

    density, cell = _read_vasp_density(source_filename)
    positive, negative = density_isosurface_primitives(
        density,
        cell,
        level=level,
        positive_material=positive_material,
        negative_material=negative_material,
        periodic=periodic,
        step_size=step_size,
        allow_degenerate=allow_degenerate,
    )
    save_isosurface_meshes(
        cache_filename,
        positive,
        negative,
        cell=cell,
        level=level,
        level_ase=vesta_level_to_ase(level),
        periodic=periodic,
        step_size=step_size,
        source_file=source_filename if include_source_hash else None,
        compressed=compressed,
        geometry_dtype=geometry_dtype,
    )
    return positive, negative


def save_isosurface_meshes(
    filename: str | PathLike[str],
    positive: TriangleMeshPrimitive,
    negative: TriangleMeshPrimitive,
    *,
    cell: ArrayLike | None = None,
    level: float | None = None,
    level_ase: float | None = None,
    periodic: bool | None = None,
    step_size: int | None = None,
    source_file: str | PathLike[str] | None = None,
    compressed: bool = True,
    geometry_dtype: np.dtype | type = np.float32,
) -> None:
    """Save positive/negative mesh geometry and provenance to a NumPy archive.

    Materials are intentionally not serialized. They are supplied when the
    cache is loaded, allowing color, transparency, and finish to change without
    recalculating the surface.

    Parameters
    ----------
    filename
        Output path. The exact path is used; ``.npz`` is not silently appended.
    positive, negative
        Isosurface primitives. Their geometry and optional normals are cached.
    cell, level, level_ase, periodic, step_size
        Optional mesh-generation metadata. ``level`` is the VESTA value in
        electrons per bohr³; ``level_ase`` is the converted value in electrons
        per ångström³.
    source_file
        Optional source VASP file. Its basename and SHA-256 digest are stored,
        but not its path or contents.
    compressed
        Use ``np.savez_compressed``. Disable for faster writes and loads.
    geometry_dtype
        Floating-point storage type for vertices and normals. ``float32`` is
        the compact default; use ``float64`` if exact double precision matters.
    """

    geometry_dtype = np.dtype(geometry_dtype)
    if geometry_dtype.kind != "f":
        raise ValueError("geometry_dtype must be a floating-point dtype")

    arrays: dict[str, np.ndarray] = {
        "cache_format": np.asarray(_CACHE_FORMAT),
        "cache_version": np.asarray(_CACHE_VERSION, dtype=np.int32),
    }
    arrays.update(_mesh_to_cache_arrays("positive", positive, geometry_dtype))
    arrays.update(_mesh_to_cache_arrays("negative", negative, geometry_dtype))

    if cell is not None:
        cell_array = np.asarray(cell, dtype=np.float64)
        if cell_array.shape != (3, 3) or not np.all(np.isfinite(cell_array)):
            raise ValueError("cell must be a finite 3 x 3 matrix")
        arrays["cell"] = cell_array
    if level is not None:
        if not np.isfinite(level) or level <= 0:
            raise ValueError("level must be a positive finite number")
        arrays["level"] = np.asarray(level, dtype=np.float64)
        arrays["level_units"] = np.asarray("electron/bohr^3")
    if level_ase is not None:
        if not np.isfinite(level_ase) or level_ase <= 0:
            raise ValueError("level_ase must be a positive finite number")
        arrays["level_ase"] = np.asarray(level_ase, dtype=np.float64)
    if periodic is not None:
        arrays["periodic"] = np.asarray(bool(periodic), dtype=np.bool_)
    if step_size is not None:
        if (
            isinstance(step_size, bool)
            or not isinstance(step_size, (int, np.integer))
            or step_size < 1
        ):
            raise ValueError("step_size must be a positive integer")
        arrays["step_size"] = np.asarray(step_size, dtype=np.int32)
    if source_file is not None:
        source_path = Path(source_file)
        arrays["source_name"] = np.asarray(source_path.name)
        arrays["source_sha256"] = np.asarray(_sha256_file(source_path))

    saver = np.savez_compressed if compressed else np.savez
    with Path(filename).open("wb") as output:
        saver(output, **arrays)


@overload
def load_isosurface_meshes(
    filename: str | PathLike[str],
    *,
    positive_material: Material = DEFAULT_POSITIVE_MATERIAL,
    negative_material: Material = DEFAULT_NEGATIVE_MATERIAL,
    return_metadata: Literal[False] = False,
) -> tuple[TriangleMeshPrimitive, TriangleMeshPrimitive]: ...


@overload
def load_isosurface_meshes(
    filename: str | PathLike[str],
    *,
    positive_material: Material = DEFAULT_POSITIVE_MATERIAL,
    negative_material: Material = DEFAULT_NEGATIVE_MATERIAL,
    return_metadata: Literal[True],
) -> tuple[
    TriangleMeshPrimitive,
    TriangleMeshPrimitive,
    IsosurfaceCacheMetadata,
]: ...


def load_isosurface_meshes(
    filename: str | PathLike[str],
    *,
    positive_material: Material = DEFAULT_POSITIVE_MATERIAL,
    negative_material: Material = DEFAULT_NEGATIVE_MATERIAL,
    return_metadata: bool = False,
) -> (
    tuple[TriangleMeshPrimitive, TriangleMeshPrimitive]
    | tuple[
        TriangleMeshPrimitive,
        TriangleMeshPrimitive,
        IsosurfaceCacheMetadata,
    ]
):
    """Load cached geometry and reconstruct atomic-povray mesh primitives.

    The archive is always opened with ``allow_pickle=False``. Set
    ``return_metadata=True`` to receive ``(positive, negative, metadata)``.
    """

    try:
        with np.load(filename, allow_pickle=False) as archive:
            _validate_cache_header(archive)
            positive = _mesh_from_cache(
                archive,
                "positive",
                positive_material,
            )
            negative = _mesh_from_cache(
                archive,
                "negative",
                negative_material,
            )
            metadata = _metadata_from_cache(archive)
    except (OSError, TypeError, ValueError, KeyError) as error:
        if isinstance(error, ValueError) and str(error).startswith(
            "Unsupported isosurface cache"
        ):
            raise
        raise ValueError(f"Could not read isosurface cache {filename!s}") from error

    if return_metadata:
        return positive, negative, metadata
    return positive, negative


def source_matches_cache(
    source_file: str | PathLike[str],
    metadata: IsosurfaceCacheMetadata,
) -> bool | None:
    """Check a VASP file against cached provenance.

    Returns ``None`` if the cache contains no source digest.
    """

    if metadata.source_sha256 is None:
        return None
    return _sha256_file(Path(source_file)) == metadata.source_sha256


def _read_vasp_density(
    filename: str | PathLike[str],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    charge_density = VaspChargeDensity(str(filename))
    if not charge_density.chg or not charge_density.atoms:
        raise ValueError(f"No charge-density grid found in {filename!s}")
    density = np.asarray(charge_density.chg[-1], dtype=float)
    cell = np.asarray(charge_density.atoms[-1].cell.array, dtype=float)
    return density, cell


def _mesh_to_cache_arrays(
    prefix: str,
    mesh: TriangleMeshPrimitive,
    geometry_dtype: np.dtype,
) -> dict[str, np.ndarray]:
    vertices = np.asarray(mesh.vertices, dtype=geometry_dtype)
    faces = np.asarray(mesh.faces, dtype=np.int64)
    if vertices.ndim != 2 or vertices.shape[1:] != (3,):
        raise ValueError(f"{prefix} vertices must have shape (n, 3)")
    if faces.ndim != 2 or faces.shape[1:] != (3,):
        raise ValueError(f"{prefix} faces must have shape (m, 3)")
    if not np.all(np.isfinite(vertices)):
        raise ValueError(f"{prefix} vertices must contain only finite values")
    if np.any(faces < 0) or (faces.size and np.max(faces) >= len(vertices)):
        raise ValueError(f"{prefix} faces contain an invalid vertex index")
    if len(vertices) > np.iinfo(np.int32).max:
        raise ValueError(f"{prefix} mesh is too large for int32 face indices")

    arrays = {
        f"{prefix}_vertices": vertices,
        f"{prefix}_faces": faces.astype(np.int32),
        f"{prefix}_has_normals": np.asarray(
            mesh.normals is not None,
            dtype=np.bool_,
        ),
    }
    if mesh.normals is not None:
        normals = np.asarray(mesh.normals, dtype=geometry_dtype)
        if normals.shape != vertices.shape:
            raise ValueError(f"{prefix} normals must match the vertex shape")
        if not np.all(np.isfinite(normals)):
            raise ValueError(f"{prefix} normals must contain only finite values")
        arrays[f"{prefix}_normals"] = normals
    return arrays


def _validate_cache_header(archive: np.lib.npyio.NpzFile) -> None:
    cache_format = str(_scalar(archive, "cache_format"))
    cache_version = int(_scalar(archive, "cache_version"))
    if cache_format != _CACHE_FORMAT:
        raise ValueError(
            f"Unsupported isosurface cache format {cache_format!r}"
        )
    if cache_version not in (1, _CACHE_VERSION):
        raise ValueError(
            "Unsupported isosurface cache version "
            f"{cache_version}; expected 1 or {_CACHE_VERSION}"
        )


def _mesh_from_cache(
    archive: np.lib.npyio.NpzFile,
    prefix: str,
    material: Material,
) -> TriangleMeshPrimitive:
    vertices = np.asarray(archive[f"{prefix}_vertices"])
    faces = np.asarray(archive[f"{prefix}_faces"])
    has_normals = bool(_scalar(archive, f"{prefix}_has_normals"))

    if vertices.ndim != 2 or vertices.shape[1:] != (3,):
        raise ValueError(f"Invalid {prefix} vertex array")
    if faces.ndim != 2 or faces.shape[1:] != (3,):
        raise ValueError(f"Invalid {prefix} face array")
    if not np.issubdtype(vertices.dtype, np.floating):
        raise ValueError(f"Invalid {prefix} vertex dtype")
    if not np.issubdtype(faces.dtype, np.integer):
        raise ValueError(f"Invalid {prefix} face dtype")
    if not np.all(np.isfinite(vertices)):
        raise ValueError(f"Invalid {prefix} vertex values")
    if np.any(faces < 0) or (faces.size and np.max(faces) >= len(vertices)):
        raise ValueError(f"Invalid {prefix} face indices")

    normals = None
    if has_normals:
        normals = np.asarray(archive[f"{prefix}_normals"])
        if normals.shape != vertices.shape:
            raise ValueError(f"Invalid {prefix} normal array")
        if not np.issubdtype(normals.dtype, np.floating):
            raise ValueError(f"Invalid {prefix} normal dtype")
        if not np.all(np.isfinite(normals)):
            raise ValueError(f"Invalid {prefix} normal values")

    return TriangleMeshPrimitive(
        vertices=_vectors_as_tuples(vertices),
        faces=tuple(tuple(int(index) for index in face) for face in faces),
        material=material,
        normals=None if normals is None else _vectors_as_tuples(normals),
    )


def _metadata_from_cache(
    archive: np.lib.npyio.NpzFile,
) -> IsosurfaceCacheMetadata:
    cell = None
    if "cell" in archive:
        cell_array = np.asarray(archive["cell"], dtype=float)
        if cell_array.shape != (3, 3) or not np.all(np.isfinite(cell_array)):
            raise ValueError("Invalid cached cell")
        cell = _vectors_as_tuples(cell_array)

    format_version = int(_scalar(archive, "cache_version"))
    return IsosurfaceCacheMetadata(
        format_version=format_version,
        cell=cell,
        level=_optional_scalar(archive, "level", float),
        level_ase=(
            _optional_scalar(archive, "level_ase", float)
            if format_version >= 2
            else _optional_scalar(archive, "level", float)
        ),
        level_units=(
            _optional_scalar(archive, "level_units", str)
            if format_version >= 2
            else "electron/angstrom^3"
        ),
        periodic=_optional_scalar(archive, "periodic", bool),
        step_size=_optional_scalar(archive, "step_size", int),
        source_name=_optional_scalar(archive, "source_name", str),
        source_sha256=_optional_scalar(archive, "source_sha256", str),
    )


def _scalar(archive: np.lib.npyio.NpzFile, key: str) -> object:
    value = np.asarray(archive[key])
    if value.shape != ():
        raise ValueError(f"Invalid scalar cache field {key!r}")
    return value.item()


def _optional_scalar(
    archive: np.lib.npyio.NpzFile,
    key: str,
    converter: type,
) -> object | None:
    if key not in archive:
        return None
    return converter(_scalar(archive, key))


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def vesta_level_to_ase(level: float) -> float:
    """Convert a VESTA VASP-density level from bohr⁻³ to ångström⁻³."""

    if not np.isfinite(level) or level <= 0:
        raise ValueError("level must be a positive finite number")
    return float(level) * VESTA_TO_ASE_DENSITY


def _validate_inputs(
    density: ArrayLike,
    cell: ArrayLike,
    *,
    level: float,
    step_size: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    density_array = np.asarray(density, dtype=float)
    cell_array = np.asarray(cell, dtype=float)

    if density_array.ndim != 3 or any(size < 2 for size in density_array.shape):
        raise ValueError("density must be a three-dimensional grid")
    if not np.all(np.isfinite(density_array)):
        raise ValueError("density must contain only finite values")
    if cell_array.shape != (3, 3) or not np.all(np.isfinite(cell_array)):
        raise ValueError("cell must be a finite 3 x 3 matrix")
    if abs(float(np.linalg.det(cell_array))) < 1e-12:
        raise ValueError("cell vectors must be linearly independent")
    if not np.isfinite(level) or level <= 0:
        raise ValueError("level must be a positive finite number")
    if isinstance(step_size, bool) or not isinstance(step_size, (int, np.integer)):
        raise ValueError("step_size must be a positive integer")
    if step_size < 1:
        raise ValueError("step_size must be a positive integer")

    return density_array, cell_array


def _isosurface_primitive(
    field: NDArray[np.float64],
    cell: NDArray[np.float64],
    *,
    level: float,
    material: Material,
    label: str,
    periodic: bool,
    step_size: int,
    allow_degenerate: bool,
) -> TriangleMeshPrimitive:
    minimum = float(np.min(field))
    maximum = float(np.max(field))
    if not minimum <= level <= maximum:
        signed_level = level if label == "positive" else -level
        raise ValueError(
            f"The {label} isosurface at {signed_level:g} is absent; "
            f"density range is {minimum:g} to {maximum:g} after sign mapping"
        )

    marching_field = (
        np.pad(field, ((0, 1), (0, 1), (0, 1)), mode="wrap")
        if periodic
        else field
    )
    vertices, faces, fallback_normals, _ = marching_cubes(
        marching_field,
        level=level,
        step_size=step_size,
        allow_degenerate=allow_degenerate,
        gradient_direction="descent",
    )

    grid_shape = np.asarray(field.shape, dtype=float)
    fractional_vertices = vertices / grid_shape
    cartesian_vertices = fractional_vertices @ cell

    grid_normals = _periodic_outward_normals(field, vertices, periodic=periodic)
    zero_normals = np.linalg.norm(grid_normals, axis=1) < 1e-14
    grid_normals[zero_normals] = fallback_normals[zero_normals]

    # Grid-index positions transform as
    # x_cart = x_grid @ diag(1 / grid_shape) @ cell. Plane normals therefore
    # acquire the grid-shape factors before the inverse-transpose cell map.
    cartesian_normals = (
        grid_normals * grid_shape[np.newaxis, :]
    ) @ np.linalg.inv(cell).T
    lengths = np.linalg.norm(cartesian_normals, axis=1)
    if np.any(lengths < 1e-14):
        raise ValueError("Could not determine a normal for every mesh vertex")
    cartesian_normals /= lengths[:, np.newaxis]

    # A left-handed cell reverses triangle winding under the affine transform.
    if np.linalg.det(cell) < 0:
        faces = faces[:, (0, 2, 1)]

    return TriangleMeshPrimitive(
        vertices=_vectors_as_tuples(cartesian_vertices),
        faces=tuple(tuple(int(index) for index in face) for face in faces),
        material=material,
        normals=_vectors_as_tuples(cartesian_normals),
    )


def _periodic_outward_normals(
    field: NDArray[np.float64],
    vertices: NDArray[np.float64],
    *,
    periodic: bool,
) -> NDArray[np.float64]:
    if periodic:
        gradients = np.stack(
            [
                0.5
                * (
                    np.roll(field, -1, axis=axis)
                    - np.roll(field, 1, axis=axis)
                )
                for axis in range(3)
            ],
            axis=-1,
        )
    else:
        gradients = np.stack(
            np.gradient(field, edge_order=1),
            axis=-1,
        )

    # Regions with field >= level are the inside of both signed meshes.
    # Their outward direction therefore points toward decreasing field.
    return -_trilinear_vectors(gradients, vertices, periodic=periodic)


def _trilinear_vectors(
    vectors: NDArray[np.float64],
    points: NDArray[np.float64],
    *,
    periodic: bool,
) -> NDArray[np.float64]:
    shape = np.asarray(vectors.shape[:3], dtype=int)
    if periodic:
        sample_points = np.mod(points, shape)
    else:
        sample_points = np.clip(points, 0.0, shape - 1)

    lower = np.floor(sample_points).astype(int)
    fraction = sample_points - lower
    result = np.zeros((len(points), 3), dtype=float)

    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                offset = np.array((dx, dy, dz), dtype=int)
                indices = lower + offset
                if periodic:
                    indices %= shape
                else:
                    indices = np.minimum(indices, shape - 1)
                weights = np.prod(
                    np.where(offset, fraction, 1.0 - fraction),
                    axis=1,
                )
                result += weights[:, np.newaxis] * vectors[
                    indices[:, 0],
                    indices[:, 1],
                    indices[:, 2],
                ]
    return result


def _vectors_as_tuples(
    vectors: NDArray[np.float64],
) -> tuple[tuple[float, float, float], ...]:
    return tuple(tuple(float(value) for value in vector) for vector in vectors)
