"""Structure input through ASE."""

from __future__ import annotations

from os import PathLike

from ase.io import read

from .model import StructureModel


def load_structure(
    filename: str | PathLike[str],
    *,
    format: str | None = None,
    index: int = -1,
) -> StructureModel:
    """Read one structure using ASE.

    The old ``.povin`` format is intentionally unsupported.
    """

    path = str(filename)
    if path.lower().endswith(".povin"):
        raise ValueError(
            "The legacy .povin format is not supported; use the original "
            "POSCAR/CONTCAR or another ASE-readable structure."
        )
    atoms = read(path, format=format, index=index)
    return StructureModel(atoms=atoms, source=path)

