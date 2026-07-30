"""Convert structural geometry to generic render primitives."""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from ..model import GeometryModel
from ..primitives import (
    Color,
    CylinderPrimitive,
    Finish,
    Material,
    Primitive,
    SpherePrimitive,
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

    def atom_style(self, symbol: str) -> AtomStyle:
        return self.elements.get(symbol, self.default_atom)

    def bond_style(self, rule_id: str) -> BondStyle:
        return self.bonds.get(rule_id, self.default_bond)


@dataclass(frozen=True)
class StyledGeometry:
    geometry: GeometryModel
    primitives: tuple[Primitive, ...]


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
    return StyledGeometry(geometry, tuple(primitives))
