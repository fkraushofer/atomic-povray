"""Convert structural geometry to generic render primitives."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import exp
from typing import Literal

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
    1/e. Points before the plane retain their original material. Directional
    lighting and highlights fade faster than color so distant primitives
    flatten into ``target``. Alpha is preserved unless ``shade_alpha`` is true.
    """

    origin: Vec3
    direction: Vec3
    decay_length: float
    target: Color
    shade_alpha: bool = False

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

    def factor_at(self, position: Vec3) -> float:
        """Return the surviving foreground fraction at ``position``."""
        direction = np.asarray(self.direction, dtype=float)
        axis = direction / np.linalg.norm(direction)
        depth = max(
            0.0,
            float(np.dot(np.asarray(position, dtype=float) - self.origin, axis)),
        )
        return exp(-depth / self.decay_length)

    def color_at(self, color: Color, position: Vec3) -> Color:
        """Return ``color`` exponentially blended toward the target color."""

        original_fraction = self.factor_at(position)
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
            alpha=(
                original_fraction * color.alpha
                + target_fraction * self.target.alpha
                if self.shade_alpha
                else color.alpha
            ),
        )

    def material_at(self, material: Material, position: Vec3) -> Material:
        """Fade a material using the legacy fog-like finish response."""

        factor = self.factor_at(position)
        factor_squared = factor * factor
        return replace(
            material,
            color=self.color_at(material.color, position),
            # Suppress lighting and flatten the primitive with emission, which
            # unlike ambient is not scaled by the scene's ambient_light.
            ambient=material.ambient * factor_squared,
            emission=(
                material.emission * factor_squared + (1.0 - factor_squared)
            ),
            diffuse=material.diffuse * factor_squared,
            phong=material.phong * factor_squared,
            specular=material.specular * factor_squared * factor,
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
    style: Literal["solid", "dashed"] = "solid"
    dashes: int = 4

    def __post_init__(self) -> None:
        if self.style not in ("solid", "dashed"):
            raise ValueError("style must be 'solid' or 'dashed'")
        if isinstance(self.dashes, bool) or not isinstance(self.dashes, int):
            raise TypeError("dashes must be an integer")
        if self.dashes < 1:
            raise ValueError("dashes must be at least 1")

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
        material = shading.material_at(primitive.material, position)
        primitives[index] = replace(primitive, material=material)


def _bond_spans(
    start: Vec3,
    end: Vec3,
    style_a: AtomStyle,
    style_b: AtomStyle,
    bond_style: BondStyle,
) -> tuple[tuple[np.ndarray, np.ndarray], ...]:
    position_a = np.asarray(start, dtype=float)
    position_b = np.asarray(end, dtype=float)
    if bond_style.style == "solid":
        return ((position_a, position_b),)

    vector = position_b - position_a
    length = float(np.linalg.norm(vector))
    visible_length = length - style_a.radius - style_b.radius
    if length == 0.0 or visible_length <= 0.0:
        return ()

    direction = vector / length
    visible_start = position_a + style_a.radius * direction
    dash_length = visible_length / (2 * bond_style.dashes - 1)
    return tuple(
        (
            visible_start + 2 * index * dash_length * direction,
            visible_start + (2 * index + 1) * dash_length * direction,
        )
        for index in range(bond_style.dashes)
    )


def _bond_primitives(
    start: Vec3,
    end: Vec3,
    style_a: AtomStyle,
    style_b: AtomStyle,
    bond_style: BondStyle,
    default_finish: Finish,
) -> tuple[CylinderPrimitive, ...]:
    spans = _bond_spans(start, end, style_a, style_b, bond_style)
    if (
        bond_style.color is not None
        or bond_style.material is not None
        or not bond_style.split_by_atom_color
    ):
        material = bond_style.material_for(style_a.color, default_finish)
        return tuple(
            CylinderPrimitive(
                tuple(float(value) for value in span_start),
                tuple(float(value) for value in span_end),
                bond_style.radius,
                material,
            )
            for span_start, span_end in spans
        )

    position_a = np.asarray(start, dtype=float)
    position_b = np.asarray(end, dtype=float)
    length = float(np.linalg.norm(position_b - position_a))
    if length == 0.0:
        return ()
    split_fraction = (length + style_a.radius - style_b.radius) / (2 * length)
    split_fraction = float(np.clip(split_fraction, 0.0, 1.0))
    split_point = position_a + split_fraction * (position_b - position_a)
    direction = (position_b - position_a) / length
    split_coordinate = float(np.dot(split_point - position_a, direction))

    primitives: list[CylinderPrimitive] = []
    material_a = bond_style.material_for(style_a.color, default_finish)
    material_b = bond_style.material_for(style_b.color, default_finish)
    for span_start, span_end in spans:
        start_coordinate = float(np.dot(span_start - position_a, direction))
        end_coordinate = float(np.dot(span_end - position_a, direction))
        if start_coordinate < split_coordinate:
            piece_end = (
                span_end if end_coordinate <= split_coordinate else split_point
            )
            primitives.append(
                CylinderPrimitive(
                    tuple(float(value) for value in span_start),
                    tuple(float(value) for value in piece_end),
                    bond_style.radius,
                    material_a,
                )
            )
        if end_coordinate > split_coordinate:
            piece_start = (
                span_start if start_coordinate >= split_coordinate else split_point
            )
            primitives.append(
                CylinderPrimitive(
                    tuple(float(value) for value in piece_start),
                    tuple(float(value) for value in span_end),
                    bond_style.radius,
                    material_b,
                )
            )
    return tuple(primitives)


def apply_styles(geometry: GeometryModel, styles: StyleConfig) -> StyledGeometry:
    """Create spheres and solid or dashed bond cylinders."""

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

        primitives.extend(
            _bond_primitives(
                atom_a.position,
                atom_b.position,
                style_a,
                style_b,
                bond_style,
                styles.default_finish,
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
