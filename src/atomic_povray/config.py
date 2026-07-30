"""Validated configuration objects for geometry construction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

from .model import Vec3

CoordinateSpace = Literal["cartesian", "fractional"]
BondExtensionMode = Literal["asymmetric", "symmetric", "none"]


@dataclass(frozen=True)
class BondRule:
    """A distance rule for a pair of elements.

    The order of ``element_a`` and ``element_b`` only matters at a boundary.
    With the default ``extension_mode="asymmetric"``, an in-bounds
    ``element_a`` atom may pull in an out-of-bounds ``element_b`` atom, but not
    vice versa. This matches VESTA's default Fe-O-style behavior.
    """

    element_a: str
    element_b: str
    min_distance: float
    max_distance: float
    name: str | None = None
    extension_mode: BondExtensionMode = "asymmetric"

    def __post_init__(self) -> None:
        if self.min_distance < 0:
            raise ValueError("min_distance must be non-negative")
        if self.max_distance <= self.min_distance:
            raise ValueError("max_distance must be larger than min_distance")
        if self.extension_mode not in ("asymmetric", "symmetric", "none"):
            raise ValueError(
                "extension_mode must be 'asymmetric', 'symmetric', or 'none'"
            )

    @property
    def rule_id(self) -> str:
        return self.name or f"{self.element_a}-{self.element_b}"

    def matches(self, symbol_a: str, symbol_b: str, distance: float) -> bool:
        elements_match = (
            symbol_a == self.element_a and symbol_b == self.element_b
        ) or (symbol_a == self.element_b and symbol_b == self.element_a)
        return elements_match and self.min_distance <= distance <= self.max_distance

    def allows_extension_from(self, anchor: str, extension: str) -> bool:
        """Return whether an in-bounds anchor may add an outside endpoint."""

        if self.extension_mode == "none":
            return False
        if not (
            (anchor == self.element_a and extension == self.element_b)
            or (anchor == self.element_b and extension == self.element_a)
        ):
            return False
        return (
            self.extension_mode == "symmetric"
            or anchor == self.element_a
            or self.element_a == self.element_b
        )


@dataclass(frozen=True)
class BoundaryPlane:
    """An inclusive half-space boundary.

    Points satisfying ``normal · coordinate >= offset`` are inside. Coordinates
    may be Cartesian or fractional. Bond-extension atoms may cross this plane
    only when ``allow_bond_extensions`` is true.
    """

    normal: Vec3
    offset: float
    coordinate_space: CoordinateSpace = "cartesian"
    allow_bond_extensions: bool = True
    name: str | None = None

    def __post_init__(self) -> None:
        if len(self.normal) != 3 or np.linalg.norm(self.normal) == 0:
            raise ValueError("normal must be a non-zero three-vector")
        if self.coordinate_space not in ("cartesian", "fractional"):
            raise ValueError("coordinate_space must be 'cartesian' or 'fractional'")

    def contains(
        self,
        position: Vec3,
        fractional_position: Vec3,
        *,
        tolerance: float = 1e-9,
    ) -> bool:
        coordinate = (
            position if self.coordinate_space == "cartesian" else fractional_position
        )
        return float(np.dot(self.normal, coordinate)) >= self.offset - tolerance


@dataclass(frozen=True)
class BoundarySet:
    """A conjunction of clipping planes."""

    planes: tuple[BoundaryPlane, ...] = ()

    def contains(self, position: Vec3, fractional_position: Vec3) -> bool:
        return all(
            plane.contains(position, fractional_position) for plane in self.planes
        )

    def permits_extension(self, position: Vec3, fractional_position: Vec3) -> bool:
        """Whether every crossed plane permits a one-hop bond extension."""

        return all(
            plane.contains(position, fractional_position) or plane.allow_bond_extensions
            for plane in self.planes
        )


@dataclass(frozen=True)
class CartesianBounds:
    """Inclusive Cartesian z bounds, expressed as ordinary boundary planes."""

    z_min: float | None = None
    z_max: float | None = None
    z_min_allow_bond_extensions: bool = True
    z_max_allow_bond_extensions: bool = True

    def __post_init__(self) -> None:
        if (
            self.z_min is not None
            and self.z_max is not None
            and self.z_min > self.z_max
        ):
            raise ValueError("z_min must not exceed z_max")

    @property
    def planes(self) -> tuple[BoundaryPlane, ...]:
        planes: list[BoundaryPlane] = []
        if self.z_min is not None:
            planes.append(
                BoundaryPlane(
                    (0.0, 0.0, 1.0),
                    self.z_min,
                    allow_bond_extensions=self.z_min_allow_bond_extensions,
                    name="z_min",
                )
            )
        if self.z_max is not None:
            planes.append(
                BoundaryPlane(
                    (0.0, 0.0, -1.0),
                    -self.z_max,
                    allow_bond_extensions=self.z_max_allow_bond_extensions,
                    name="z_max",
                )
            )
        return tuple(planes)

    def contains(self, position: Vec3, fractional_position: Vec3) -> bool:
        return BoundarySet(self.planes).contains(position, fractional_position)

    def permits_extension(self, position: Vec3, fractional_position: Vec3) -> bool:
        return BoundarySet(self.planes).permits_extension(position, fractional_position)


@dataclass(frozen=True)
class ReplicationConfig:
    """Finite cell repetitions and extension policy for their six faces."""

    counts: tuple[int, int, int] = (1, 1, 1)
    lower_allow_bond_extensions: tuple[bool, bool, bool] = (True, True, True)
    upper_allow_bond_extensions: tuple[bool, bool, bool] = (True, True, True)

    def __post_init__(self) -> None:
        if len(self.counts) != 3 or any(int(count) < 1 for count in self.counts):
            raise ValueError("counts must contain three positive integers")
        if len(self.lower_allow_bond_extensions) != 3:
            raise ValueError("lower_allow_bond_extensions must contain three booleans")
        if len(self.upper_allow_bond_extensions) != 3:
            raise ValueError("upper_allow_bond_extensions must contain three booleans")
