"""Validated configuration objects for geometry construction."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable, Sequence
from typing import Literal

import numpy as np

from .model import Vec3

BondExtensionMode = Literal["asymmetric", "symmetric", "none"]
AtomSelection = int | Sequence[int] | np.ndarray
AtomSelector = Callable[[object], AtomSelection]


@dataclass(frozen=True)
class BondRule:
    """A half-open distance rule for a pair of elements.

    Distances satisfy ``min_distance <= distance < max_distance``, so adjacent
    rules can share a cutoff without matching the same bond.

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
        return elements_match and self.min_distance <= distance < self.max_distance

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
class CoordinationPolyhedronRule:
    """Select ligand environments from existing bond-rule matches."""

    center_element: str
    name: str | None = None
    ligand_elements: frozenset[str] | None = None
    bond_rules: frozenset[str] | None = None
    center_selector: AtomSelector | None = None
    boundary_mode: Literal["complete", "visible"] = "complete"
    expansion: float = 0.0
    position_tolerance: float = 1e-7
    rank_tolerance: float = 1e-7
    coplanar_angle_tolerance: float = 1e-6
    on_degenerate: Literal["warn", "error", "ignore"] = "warn"

    def __post_init__(self) -> None:
        if not self.center_element:
            raise ValueError("center_element must not be empty")
        if self.boundary_mode not in ("complete", "visible"):
            raise ValueError("boundary_mode must be 'complete' or 'visible'")
        if self.on_degenerate not in ("warn", "error", "ignore"):
            raise ValueError("on_degenerate must be 'warn', 'error', or 'ignore'")
        if self.center_selector is not None and not callable(self.center_selector):
            raise TypeError("center_selector must be callable")
        for name in ("position_tolerance", "rank_tolerance"):
            if not np.isfinite(getattr(self, name)) or getattr(self, name) <= 0:
                raise ValueError(f"{name} must be positive and finite")
        if not np.isfinite(self.coplanar_angle_tolerance) or not 0 <= self.coplanar_angle_tolerance <= np.pi:
            raise ValueError("coplanar_angle_tolerance must lie between 0 and pi")
        if not np.isfinite(self.expansion):
            raise ValueError("expansion must be finite")
        if self.ligand_elements is not None:
            object.__setattr__(self, "ligand_elements", frozenset(self.ligand_elements))
        if self.bond_rules is not None:
            object.__setattr__(self, "bond_rules", frozenset(self.bond_rules))

    @property
    def rule_id(self) -> str:
        return self.name or f"{self.center_element}-polyhedron"


@dataclass(frozen=True)
class CutoffPlane:
    """A Cartesian plane that clips everything beyond its normal direction.

    ``normal`` points toward the discarded half-space. ``distance`` is the
    perpendicular distance of the plane from the Cartesian origin, so points
    satisfying ``unit(normal) · position <= distance`` are retained.
    """

    normal: Vec3
    distance: float
    allow_bond_extensions: bool = True
    name: str | None = None

    def __post_init__(self) -> None:
        if len(self.normal) != 3 or np.linalg.norm(self.normal) == 0:
            raise ValueError("normal must be a non-zero three-vector")

    def contains(self, position: Vec3, *, tolerance: float = 1e-9) -> bool:
        unit_normal = np.asarray(self.normal, dtype=float) / np.linalg.norm(self.normal)
        return float(np.dot(unit_normal, position)) <= self.distance + tolerance


@dataclass(frozen=True)
class DisplayBounds:
    """Unified fractional display ranges and optional Cartesian cutoff planes.

    The three half-open ``fractional_ranges`` correspond to the three unit-cell
    vectors: the lower endpoint is included and the upper endpoint is excluded.
    Integer-sized ranges therefore produce exactly that many periodic copies;
    non-integer endpoints crop or offset the displayed region. Each of the six
    range faces and every cutoff plane independently controls whether a one-hop
    bond extension may cross it.
    """

    fractional_ranges: tuple[
        tuple[float, float],
        tuple[float, float],
        tuple[float, float],
    ] = ((0.0, 1.0), (0.0, 1.0), (0.0, 1.0))
    cutoff_planes: tuple[CutoffPlane, ...] = ()
    lower_allow_bond_extensions: tuple[bool, bool, bool] = (True, True, True)
    upper_allow_bond_extensions: tuple[bool, bool, bool] = (True, True, True)

    def __post_init__(self) -> None:
        if len(self.fractional_ranges) != 3:
            raise ValueError("fractional_ranges must contain three (min, max) pairs")
        for limits in self.fractional_ranges:
            if len(limits) != 2:
                raise ValueError(
                    "fractional_ranges must contain three (min, max) pairs"
                )
            if not np.isfinite(limits).all():
                raise ValueError("fractional range endpoints must be finite")
            if limits[0] > limits[1]:
                raise ValueError(
                    "fractional range minimum must not exceed its maximum"
                )
        if len(self.lower_allow_bond_extensions) != 3:
            raise ValueError("lower_allow_bond_extensions must contain three booleans")
        if len(self.upper_allow_bond_extensions) != 3:
            raise ValueError("upper_allow_bond_extensions must contain three booleans")

    def contains(
        self,
        position: Vec3,
        fractional_position: Vec3,
        *,
        tolerance: float = 1e-9,
    ) -> bool:
        within_ranges = all(
            lower - tolerance <= coordinate < upper - tolerance
            for coordinate, (lower, upper) in zip(
                fractional_position, self.fractional_ranges
            )
        )
        return within_ranges and all(
            plane.contains(position, tolerance=tolerance)
            for plane in self.cutoff_planes
        )

    def permits_extension(
        self,
        position: Vec3,
        fractional_position: Vec3,
        *,
        tolerance: float = 1e-9,
    ) -> bool:
        for axis, (coordinate, (lower, upper)) in enumerate(
            zip(fractional_position, self.fractional_ranges)
        ):
            if (
                coordinate < lower - tolerance
                and not self.lower_allow_bond_extensions[axis]
            ):
                return False
            if (
                coordinate >= upper - tolerance
                and not self.upper_allow_bond_extensions[axis]
            ):
                return False
        return all(
            plane.contains(position, tolerance=tolerance)
            or plane.allow_bond_extensions
            for plane in self.cutoff_planes
        )
