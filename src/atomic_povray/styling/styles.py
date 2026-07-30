"""Convert structural geometry to generic render primitives."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import exp

import numpy as np

from ..model import GeometryModel, Vec3
from ..primitives import (
    Color,
    CylinderPrimitive,
    Finish,
    Material,
    Primitive,
    SpherePrimitive,
    TriangleMeshPrimitive,
)


@dataclass(frozen=True)
class DepthShading:
    """Fade primitive colors along a Cartesian direction.

    ``origin`` is the onset plane and ``direction`` points toward increasing
    fade. At ``decay_length`` beyond that plane, the original color contributes
    1/e. Points before the plane retain their original color.
    """

    origin: Vec3
    direction: Vec3
    decay_length: float
    target: Color

    def __post_init__(self) -> None:
        origin = np.asarray(self.origin, dtype=float)
        direction = np.asarray(self.direction, dtype=float)
        if origin.shape != (3,) or not np.isfinite(origin).all():
            raise ValueError("origin must be a finite three-vector")
        if direction.shape != (3,) or not np.isfinite(direction).all():
            raise ValueError("direction must be a finite three-vector")
        if np.linalg.norm(direction) == 0:
            raise ValueError("direction must be non-zero")
        if not np.isfinite(self.decay_length) or self.decay_length <= 0:
            raise ValueError("decay_length must be positive and finite")

    def color_at(self, color: Color, position: Vec3) -> Color:
        """Return ``color`` exponentially blended toward the target color."""

        direction = np.asarray(self.direction, dtype=float)
        axis = direction / np.linalg.norm(direction)
        depth = max(
            0.0,
            float(np.dot(np.asarray(position, dtype=float) - self.origin, axis)),
        )
        original_fraction = exp(-depth / self.decay_length)
        target_fraction = 1.0 - original_fraction
        return Color(
            red=original_fraction * color.red + target_fraction * self.target.red,
            green=(
                original_fraction * color.green
                + target_fraction * self.target.green
            ),
            blue=(
                original_fraction * color.blue
                + target_fraction * self.target.blue
            ),
            # Depth shading changes pigment color, not physical transparency.
            alpha=color.alpha,
        )


@dataclass(frozen=True)
class AtomStyle:
    radius: float
    color: Color
    material: Material | None = None
    finish: Finish | None = None

    def resolved_material(self, default_finish: Finish | None = None) -> Material:
        if self.material is not None:
            return self.material
        return (self.finish or default_finish or Finish()).material(self.color)


@dataclass(frozen=True)
class BondStyle:
    radius: float = 0.08
    color: Color | None = None
    material: Material | None = None
    finish: Finish | None = None
    material_template: Material | None = None
    split_by_atom_color: bool = True

    def material_for(
        self,
        fallback: Color,
        default_finish: Finish | None = None,
    ) -> Material:
        if self.material is not None:
            return self.material
        if self.finish is not None:
            return self.finish.material(self.color or fallback)
        if self.material_template is not None:
            return replace(
                self.material_template,
                color=self.color or fallback,
            )
        return (default_finish or Finish()).material(self.color or fallback)


@dataclass(frozen=True)
class StyleConfig:
    elements: dict[str, AtomStyle] = field(default_factory=dict)
    bonds: dict[str, BondStyle] = field(default_factory=dict)
    default_atom: AtomStyle = AtomStyle(0.4, Color(0.65, 0.65, 0.65))
    default_bond: BondStyle = BondStyle()
    default_finish: Finish = Finish()
    depth_shading: DepthShading | None = None

    def atom_style(self, symbol: str) -> AtomStyle:
        return self.elements.get(symbol, self.default_atom)

    def bond_style(self, rule_id: str) -> BondStyle:
        return self.bonds.get(rule_id, self.default_bond)


@dataclass(frozen=True)
class StyledGeometry:
    geometry: GeometryModel
    primitives: tuple[Primitive, ...]


def _primitive_position(primitive: Primitive) -> Vec3 | None:
    if isinstance(primitive, SpherePrimitive):
        return primitive.center
    if isinstance(primitive, CylinderPrimitive):
        return tuple(
            float((start + end) / 2)
            for start, end in zip(primitive.start, primitive.end)
        )
    if isinstance(primitive, TriangleMeshPrimitive) and primitive.vertices:
        return tuple(
            float(value)
            for value in np.mean(np.asarray(primitive.vertices, dtype=float), axis=0)
        )
    return None


def _apply_depth_shading(
    primitives: list[Primitive],
    shading: DepthShading | None,
) -> None:
    if shading is None:
        return
    for index, primitive in enumerate(primitives):
        position = _primitive_position(primitive)
        if position is None:
            continue
        material = replace(
            primitive.material,
            color=shading.color_at(primitive.material.color, position),
        )
        primitives[index] = replace(primitive, material=material)


def apply_styles(geometry: GeometryModel, styles: StyleConfig) -> StyledGeometry:
    """Create spheres and one- or two-color bond cylinders."""

    primitives: list[Primitive] = []
    atom_by_key = {atom.key: atom for atom in geometry.atoms}
    atom_styles = {
        atom.key: styles.atom_style(atom.symbol) for atom in geometry.atoms
    }

    # Bonds first so spheres naturally hide cylinder ends.
    for bond in geometry.bonds:
        atom_a = atom_by_key[bond.atom_a]
        atom_b = atom_by_key[bond.atom_b]
        style_a = atom_styles[bond.atom_a]
        style_b = atom_styles[bond.atom_b]
        bond_style = styles.bond_style(bond.rule_id)

        if bond_style.color is not None or not bond_style.split_by_atom_color:
            primitives.append(
                CylinderPrimitive(
                    atom_a.position,
                    atom_b.position,
                    bond_style.radius,
                    bond_style.material_for(style_a.color, styles.default_finish),
                )
            )
        else:
            position_a = np.asarray(atom_a.position)
            position_b = np.asarray(atom_b.position)
            split_fraction = (
                bond.distance + style_a.radius - style_b.radius
            ) / (2 * bond.distance)
            split_fraction = float(np.clip(split_fraction, 0.0, 1.0))
            split_point = tuple(
                float(value)
                for value in position_a + split_fraction * (position_b - position_a)
            )
            primitives.extend(
                (
                    CylinderPrimitive(
                        atom_a.position,
                        split_point,
                        bond_style.radius,
                        bond_style.material_for(
                            style_a.color,
                            styles.default_finish,
                        ),
                    ),
                    CylinderPrimitive(
                        split_point,
                        atom_b.position,
                        bond_style.radius,
                        bond_style.material_for(
                            style_b.color,
                            styles.default_finish,
                        ),
                    ),
                )
            )

    primitives.extend(
        SpherePrimitive(
            atom.position,
            atom_styles[atom.key].radius,
            atom_styles[atom.key].resolved_material(styles.default_finish),
        )
        for atom in geometry.atoms
    )
    _apply_depth_shading(primitives, styles.depth_shading)
    return StyledGeometry(geometry, tuple(primitives))
