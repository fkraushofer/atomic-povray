"""Renderer-independent structural and geometry data models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    from ase import Atoms

Vec3 = tuple[float, float, float]
ImageShift = tuple[int, int, int]


@dataclass(frozen=True, order=True)
class AtomKey:
    """Stable identity for one displayed periodic image of a source atom."""

    source_index: int
    image_shift: ImageShift = (0, 0, 0)


@dataclass(frozen=True)
class AtomInstance:
    key: AtomKey
    symbol: str
    fractional_position: Vec3
    position: Vec3
    is_extension: bool = False


@dataclass(frozen=True)
class Bond:
    atom_a: AtomKey
    atom_b: AtomKey
    rule_id: str
    distance: float


@dataclass(frozen=True)
class BondNeighbor:
    """One bond-rule-matched neighbor in a source atom's periodic environment."""

    source_index: int
    image_shift: ImageShift
    symbol: str
    rule_id: str
    distance: float


@dataclass(frozen=True)
class StructureModel:
    """ASE structure kept by composition rather than inheritance."""

    atoms: "Atoms"
    source: str | None = None

    @property
    def cell(self) -> NDArray[np.float64]:
        return np.asarray(self.atoms.cell.array, dtype=float)


@dataclass(frozen=True)
class GeometryModel:
    """Finite displayed atoms, bonds, and complete source-atom environments."""

    structure: StructureModel
    atoms: tuple[AtomInstance, ...]
    bonds: tuple[Bond, ...]
    adjacency: tuple[tuple[int, ...], ...]
    source_environments: tuple[tuple[BondNeighbor, ...], ...] = ()

    def atom_index(self) -> dict[AtomKey, int]:
        return {atom.key: index for index, atom in enumerate(self.atoms)}

    @property
    def primary_atoms(self) -> tuple[AtomInstance, ...]:
        return tuple(atom for atom in self.atoms if not atom.is_extension)

    @property
    def extension_atoms(self) -> tuple[AtomInstance, ...]:
        return tuple(atom for atom in self.atoms if atom.is_extension)

    def coordination(self, atom: int | AtomKey) -> int:
        index = atom if isinstance(atom, int) else self.atom_index()[atom]
        return len(self.adjacency[index])
