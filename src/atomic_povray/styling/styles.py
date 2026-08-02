"""Convert structural geometry to generic render primitives."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from math import exp, isfinite
from numbers import Real
from typing import TYPE_CHECKING, Literal, TypeAlias

import numpy as np

from ..defaults import (
    DEFAULT_HYDROGEN_BOND_RULE_ID,
    default_atom_color,
    default_atom_radius,
)
from ..model import AtomKey, BondNeighbor, GeometryModel, Vec3
from ..primitives import (
    Color,
    CylinderPrimitive,
    Finish,
    Material,
    Primitive,
    SpherePrimitive,
    TriangleMeshPrimitive,
)

if TYPE_CHECKING:
    from ase import Atoms


AtomSelection: TypeAlias = int | Sequence[int] | np.ndarray
AtomSelector: TypeAlias = Callable[["Atoms"], AtomSelection]


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
            filter=(
                original_fraction * color.filter
                + target_fraction * self.target.filter
                if self.shade_alpha
                else color.filter
            ),
            transmit=(
                original_fraction * color.transmit
                + target_fraction * self.target.transmit
                if self.shade_alpha
                else color.transmit
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
    """Atom appearance with optional radius/color for element overrides."""

    radius: float | None = None
    color: Color | None = None
    material: Material | None = None
    finish: Finish | None = None
    visible: bool = True

    def resolved_material(self, default_finish: Finish | None = None) -> Material:
        if self.material is not None:
            return self.material
        if self.color is None:
            raise ValueError("AtomStyle must be resolved before creating a material")
        return (self.finish or default_finish or Finish()).material(self.color)


@dataclass(frozen=True)
class AtomStyleOverride:
    """Partial atom style applied without repeating unchanged properties."""

    radius: float | None = None
    color: Color | None = None
    material: Material | None = None
    finish: Finish | None = None
    visible: bool | None = None

    def apply(self, style: AtomStyle) -> AtomStyle:
        changes = {
            name: value
            for name, value in (
                ("radius", self.radius),
                ("color", self.color),
                ("material", self.material),
                ("finish", self.finish),
                ("visible", self.visible),
            )
            if value is not None
        }
        return replace(style, **changes)


@dataclass(frozen=True)
class CoordinationStyleRule:
    """Apply an override to atoms with a matching bond-defined environment."""

    element: str
    coordination: int
    style: AtomStyleOverride
    neighbor_elements: frozenset[str] | None = None
    bond_rules: frozenset[str] | None = None

    def __post_init__(self) -> None:
        if not self.element:
            raise ValueError("element must not be empty")
        if isinstance(self.coordination, bool) or not isinstance(
            self.coordination, int
        ):
            raise TypeError("coordination must be an integer")
        if self.coordination < 0:
            raise ValueError("coordination must be non-negative")
        if self.neighbor_elements is not None:
            object.__setattr__(
                self, "neighbor_elements", frozenset(self.neighbor_elements)
            )
        if self.bond_rules is not None:
            object.__setattr__(self, "bond_rules", frozenset(self.bond_rules))

    def matches(self, neighbors: Iterable[BondNeighbor]) -> bool:
        count = sum(
            1
            for neighbor in neighbors
            if (
                self.neighbor_elements is None
                or neighbor.symbol in self.neighbor_elements
            )
            and (
                self.bond_rules is None
                or neighbor.rule_id in self.bond_rules
            )
        )
        return count == self.coordination


@dataclass(frozen=True)
class AtomSelectionRule:
    """Apply an override to source atoms selected from the original ASE Atoms."""

    selector: AtomSelector
    style: AtomStyleOverride

    def __post_init__(self) -> None:
        if not callable(self.selector):
            raise TypeError("selector must be callable")


@dataclass(frozen=True)
class BondStyle:
    radius: float = 0.08
    color: Color | None = None
    material: Material | None = None
    finish: Finish | None = None
    material_template: Material | None = None
    split_by_atom_color: bool = True
    style: Literal["solid", "dashed", "dotted"] = "solid"
    segments: int = 4

    def __post_init__(self) -> None:
        if self.style not in ("solid", "dashed", "dotted"):
            raise ValueError("style must be 'solid', 'dashed', or 'dotted'")
        if isinstance(self.segments, bool) or not isinstance(self.segments, int):
            raise TypeError("segments must be an integer")
        if self.segments < 1:
            raise ValueError("segments must be at least 1")
        if (
            self.style != "solid"
            and self.split_by_atom_color
            and self.color is None
            and self.material is None
        ):
            raise ValueError(
                "dashed and dotted bonds must be single-color; set color or "
                "material, or set split_by_atom_color=False"
            )

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
class PolyhedronEdgeStyle:
    visible: bool = False
    radius: float = 0.025
    color: Color | None = None
    material: Material | None = None
    finish: Finish | None = None

    def __post_init__(self) -> None:
        if not isfinite(self.radius) or self.radius <= 0:
            raise ValueError("Polyhedron edge radius must be positive and finite")

    def material_for(self, fallback: Color, default_finish: Finish) -> Material:
        if self.material is not None:
            return self.material
        return (self.finish or default_finish).material(self.color or fallback)


@dataclass(frozen=True)
class PolyhedronStyle:
    visible: bool = True
    color: Color | None = None
    material: Material | None = None
    finish: Finish | None = None
    filter: float | None = None
    transmit: float | None = None
    alpha: float | None = None
    edges: PolyhedronEdgeStyle = PolyhedronEdgeStyle()

    def __post_init__(self) -> None:
        if self.alpha is not None and self.transmit is not None:
            raise ValueError("alpha and transmit are aliases; pass only one")
        for name, value in (
            ("filter", self.filter),
            ("transmit", self.transmit),
            ("alpha", self.alpha),
        ):
            if value is not None and not 0 <= value <= 1:
                raise ValueError(f"Polyhedron {name} must lie between 0 and 1")

    def material_for(self, fallback: Color, default_finish: Finish) -> Material:
        if self.material is not None:
            return self.material
        color = self.color or fallback
        if self.filter is not None or self.transmit is not None or self.alpha is not None:
            transmit = self.transmit
            if self.alpha is not None:
                transmit = 1.0 - self.alpha
            color = Color(
                color.red,
                color.green,
                color.blue,
                filter=color.filter if self.filter is None else self.filter,
                transmit=color.transmit if transmit is None else transmit,
            )
        return (self.finish or default_finish).material(color)


@dataclass(frozen=True)
class PolyhedronStyleOverride:
    visible: bool | None = None
    color: Color | None = None
    material: Material | None = None
    finish: Finish | None = None
    filter: float | None = None
    transmit: float | None = None
    alpha: float | None = None
    edges: PolyhedronEdgeStyle | None = None

    def __post_init__(self) -> None:
        if self.alpha is not None and self.transmit is not None:
            raise ValueError("alpha and transmit are aliases; pass only one")
        for name, value in (
            ("filter", self.filter),
            ("transmit", self.transmit),
            ("alpha", self.alpha),
        ):
            if value is not None and not 0 <= value <= 1:
                raise ValueError(f"Polyhedron {name} must lie between 0 and 1")

    def apply(self, style: PolyhedronStyle) -> PolyhedronStyle:
        changes = {
                name: value
                for name, value in (
                    ("visible", self.visible),
                    ("color", self.color),
                    ("material", self.material),
                    ("finish", self.finish),
                    ("filter", self.filter),
                    ("transmit", self.transmit),
                    ("alpha", self.alpha),
                    ("edges", self.edges),
                )
                if value is not None
            }
        if self.alpha is not None:
            changes["transmit"] = None
        elif self.transmit is not None:
            changes["alpha"] = None
        return replace(style, **changes)


DEFAULT_HYDROGEN_BOND_STYLE = BondStyle(
    radius=0.05,
    color=Color(0.5, 0.5, 0.5),
    style="dashed",
    segments=4,
)


@dataclass(frozen=True)
class StyleConfig:
    preset_style: Literal[
        "ball_and_stick", "space_filling", "polyhedral"
    ] = "ball_and_stick"
    atom_size_scale: float | None = None
    bond_size_scale: float = 1.0
    draw_atoms: bool = True
    draw_bonds: bool | None = None
    draw_polyhedra: bool = True
    ambient_scale: float = 1.0
    elements: dict[str, AtomStyle] = field(default_factory=dict)
    bonds: dict[str, BondStyle] = field(default_factory=dict)
    polyhedra: dict[str, PolyhedronStyle] = field(default_factory=dict)
    coordination_rules: tuple[CoordinationStyleRule, ...] = ()
    selection_rules: tuple[AtomSelectionRule, ...] = ()
    source_atom_overrides: dict[int, AtomStyleOverride] = field(
        default_factory=dict
    )
    atom_instance_overrides: dict[AtomKey, AtomStyleOverride] = field(
        default_factory=dict
    )
    polyhedron_source_overrides: dict[int, PolyhedronStyleOverride] = field(
        default_factory=dict
    )
    polyhedron_instance_overrides: dict[AtomKey, PolyhedronStyleOverride] = field(
        default_factory=dict
    )
    default_atom: AtomStyle = AtomStyle()
    default_bond: BondStyle = BondStyle()
    default_polyhedron: PolyhedronStyle = PolyhedronStyle()
    default_atom_finish: Finish = Finish(phong=0.3)
    default_bond_finish: Finish = Finish()
    default_polyhedron_finish: Finish = Finish(phong=0.15)
    default_finish: Finish | None = None
    depth_shading: DepthShading | None = None

    def __post_init__(self) -> None:
        scales = {
            "ball_and_stick": 0.4,
            "space_filling": 1.0,
            "polyhedral": 0.4,
        }
        try:
            preset_scale = scales[self.preset_style]
        except KeyError:
            raise ValueError(
                "preset_style must be 'ball_and_stick', 'space_filling', or "
                "'polyhedral'"
            ) from None

        atom_scale = self.atom_size_scale
        if atom_scale is None:
            atom_scale = preset_scale
        self._validate_size_scale("atom_size_scale", atom_scale)
        self._validate_size_scale("bond_size_scale", self.bond_size_scale)
        self._validate_ambient_scale(self.ambient_scale)
        object.__setattr__(self, "atom_size_scale", float(atom_scale))
        object.__setattr__(self, "bond_size_scale", float(self.bond_size_scale))
        object.__setattr__(self, "ambient_scale", float(self.ambient_scale))
        if self.draw_bonds is None:
            object.__setattr__(
                self,
                "draw_bonds",
                self.preset_style in ("ball_and_stick", "polyhedral"),
            )

    @staticmethod
    def _validate_size_scale(name: str, scale: float) -> None:
        if isinstance(scale, bool) or not isinstance(scale, Real):
            raise TypeError(f"{name} must be a real number")
        if not isfinite(scale) or scale <= 0:
            raise ValueError(f"{name} must be positive and finite")

    @staticmethod
    def _validate_ambient_scale(scale: float) -> None:
        if isinstance(scale, bool) or not isinstance(scale, Real):
            raise TypeError("ambient_scale must be a real number")
        if not isfinite(scale) or scale < 0:
            raise ValueError("ambient_scale must be non-negative and finite")

    @property
    def atom_finish(self) -> Finish:
        """Return the atom finish, honoring the legacy shared override."""

        return self.default_finish or self.default_atom_finish

    @property
    def bond_finish(self) -> Finish:
        """Return the bond finish, honoring the legacy shared override."""

        return self.default_finish or self.default_bond_finish

    @property
    def polyhedron_finish(self) -> Finish:
        return self.default_finish or self.default_polyhedron_finish

    def atom_style(self, symbol: str) -> AtomStyle:
        """Resolve built-in, global, and element radius/color defaults."""

        element = self.elements.get(symbol)
        global_default = self.default_atom
        return AtomStyle(
            radius=(
                element.radius
                if element is not None and element.radius is not None
                else global_default.radius
                if global_default.radius is not None
                else default_atom_radius(symbol)
            ),
            color=(
                element.color
                if element is not None and element.color is not None
                else global_default.color
                if global_default.color is not None
                else default_atom_color(symbol)
            ),
            material=(
                element.material
                if element is not None and element.material is not None
                else global_default.material
            ),
            finish=(
                element.finish
                if element is not None and element.finish is not None
                else global_default.finish
            ),
            visible=element.visible if element is not None else global_default.visible,
        )

    def bond_style(self, rule_id: str) -> BondStyle:
        if rule_id in self.bonds:
            return self.bonds[rule_id]
        if rule_id == DEFAULT_HYDROGEN_BOND_RULE_ID:
            return DEFAULT_HYDROGEN_BOND_STYLE
        return self.default_bond

    def polyhedron_style(
        self, rule_id: str, center: AtomKey
    ) -> PolyhedronStyle:
        style = self.polyhedra.get(rule_id, self.default_polyhedron)
        source_override = self.polyhedron_source_overrides.get(center.source_index)
        if source_override is not None:
            style = source_override.apply(style)
        instance_override = self.polyhedron_instance_overrides.get(center)
        if instance_override is not None:
            style = instance_override.apply(style)
        return style


@dataclass(frozen=True)
class StyledGeometry:
    geometry: GeometryModel
    primitives: tuple[Primitive, ...]
    atom_styles: dict[AtomKey, AtomStyle] = field(default_factory=dict)


def _selected_source_indices(
    selection: AtomSelection,
    atom_count: int,
) -> frozenset[int]:
    if isinstance(selection, (int, np.integer)) and not isinstance(selection, bool):
        values = np.asarray([selection])
    else:
        values = np.asarray(selection)

    if values.dtype.kind == "b":
        if values.shape != (atom_count,):
            raise ValueError(
                "Boolean atom selector masks must have shape "
                f"({atom_count},), got {values.shape}"
            )
        return frozenset(int(index) for index in np.flatnonzero(values))

    if values.size == 0:
        return frozenset()
    if values.ndim != 1 or values.dtype.kind not in "iu":
        raise TypeError(
            "Atom selectors must return an integer index, a one-dimensional "
            "integer sequence, or a one-dimensional Boolean mask"
        )
    if np.any(values < 0) or np.any(values >= atom_count):
        raise IndexError(
            f"Atom selector indices must lie between 0 and {atom_count - 1}"
        )
    return frozenset(int(value) for value in values)


def resolve_atom_styles(
    geometry: GeometryModel,
    styles: StyleConfig,
) -> dict[AtomKey, AtomStyle]:
    """Resolve atom styles in documented order before creating primitives."""

    source_count = len(geometry.structure.atoms)
    selections = tuple(
        _selected_source_indices(
            rule.selector(geometry.structure.atoms),
            source_count,
        )
        for rule in styles.selection_rules
    )
    environments = (
        geometry.source_environments
        if geometry.source_environments
        else tuple(() for _ in range(source_count))
    )

    resolved: dict[AtomKey, AtomStyle] = {}
    for atom in geometry.atoms:
        style = styles.atom_style(atom.symbol)
        source_index = atom.key.source_index

        for rule in styles.coordination_rules:
            if (
                atom.symbol == rule.element
                and rule.matches(environments[source_index])
            ):
                style = rule.style.apply(style)

        for rule, selected in zip(styles.selection_rules, selections):
            if source_index in selected:
                style = rule.style.apply(style)

        source_override = styles.source_atom_overrides.get(source_index)
        if source_override is not None:
            style = source_override.apply(style)

        instance_override = styles.atom_instance_overrides.get(atom.key)
        if instance_override is not None:
            style = instance_override.apply(style)

        resolved[atom.key] = replace(
            style,
            radius=style.radius * styles.atom_size_scale,
        )
    return resolved


def _primitive_position(primitive: Primitive) -> Vec3 | None:
    if isinstance(primitive, SpherePrimitive):
        return primitive.center
    if isinstance(primitive, CylinderPrimitive):
        return tuple(
            float((start + end) / 2)
            for start, end in zip(primitive.start, primitive.end)
        )
    if isinstance(primitive, TriangleMeshPrimitive) and primitive.vertices:
        if primitive.reference_position is not None:
            return primitive.reference_position
        return tuple(
            float(value)
            for value in np.mean(np.asarray(primitive.vertices, dtype=float), axis=0)
        )
    return None


def _apply_ambient_scale(
    primitives: list[Primitive],
    scale: float,
) -> None:
    for index, primitive in enumerate(primitives):
        primitives[index] = replace(
            primitive,
            material=replace(
                primitive.material,
                ambient=primitive.material.ambient * scale,
            ),
        )


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
    dash_length = visible_length / (2 * bond_style.segments - 1)
    return tuple(
        (
            visible_start + 2 * index * dash_length * direction,
            visible_start + (2 * index + 1) * dash_length * direction,
        )
        for index in range(bond_style.segments)
    )


def _dotted_bond_primitives(
    start: Vec3,
    end: Vec3,
    style_a: AtomStyle,
    style_b: AtomStyle,
    bond_style: BondStyle,
    default_finish: Finish,
) -> tuple[SpherePrimitive, ...]:
    position_a = np.asarray(start, dtype=float)
    position_b = np.asarray(end, dtype=float)
    vector = position_b - position_a
    length = float(np.linalg.norm(vector))
    if length == 0.0:
        return ()

    first_distance = style_a.radius + bond_style.radius
    last_distance = length - style_b.radius - bond_style.radius
    if first_distance > last_distance:
        return ()

    if bond_style.segments == 1:
        distances = np.asarray([(first_distance + last_distance) / 2])
    else:
        distances = np.linspace(
            first_distance,
            last_distance,
            bond_style.segments,
        )

    direction = vector / length
    material = bond_style.material_for(style_a.color, default_finish)
    return tuple(
        SpherePrimitive(
            tuple(float(value) for value in position_a + distance * direction),
            bond_style.radius,
            material,
        )
        for distance in distances
    )


def _bond_primitives(
    start: Vec3,
    end: Vec3,
    style_a: AtomStyle,
    style_b: AtomStyle,
    bond_style: BondStyle,
    default_finish: Finish,
) -> tuple[Primitive, ...]:
    if bond_style.style == "dotted":
        return _dotted_bond_primitives(
            start,
            end,
            style_a,
            style_b,
            bond_style,
            default_finish,
        )

    spans = _bond_spans(start, end, style_a, style_b, bond_style)
    if (
        bond_style.style == "dashed"
        or bond_style.color is not None
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
    """Resolve atom rules, then create bond, polyhedron, and atom primitives."""

    primitives: list[Primitive] = []
    atom_by_key = {atom.key: atom for atom in geometry.atoms}
    atom_styles = resolve_atom_styles(geometry, styles)

    # Bonds first so atom spheres naturally hide solid-cylinder ends.
    for bond in (geometry.bonds if styles.draw_bonds else ()):
        atom_a = atom_by_key[bond.atom_a]
        atom_b = atom_by_key[bond.atom_b]
        style_a = atom_styles[bond.atom_a]
        style_b = atom_styles[bond.atom_b]
        if not style_a.visible or not style_b.visible:
            continue
        bond_style = styles.bond_style(bond.rule_id)
        bond_style = replace(
            bond_style,
            radius=bond_style.radius * styles.bond_size_scale,
        )

        primitives.extend(
            _bond_primitives(
                atom_a.position,
                atom_b.position,
                style_a,
                style_b,
                bond_style,
                styles.bond_finish,
            )
        )

    if styles.draw_polyhedra:
        for polyhedron in geometry.polyhedra:
            center = atom_by_key[polyhedron.center]
            center_style = atom_styles[polyhedron.center]
            polyhedron_style = styles.polyhedron_style(
                polyhedron.rule_id, polyhedron.center
            )
            if not polyhedron_style.visible:
                continue
            material = polyhedron_style.material_for(
                center_style.color, styles.polyhedron_finish
            )
            primitives.append(
                TriangleMeshPrimitive(
                    vertices=polyhedron.vertices,
                    faces=polyhedron.faces,
                    material=material,
                    reference_position=center.position,
                )
            )
            edge_style = polyhedron_style.edges
            if edge_style.visible:
                edge_material = edge_style.material_for(
                    material.color, styles.polyhedron_finish
                )
                primitives.extend(
                    CylinderPrimitive(
                        start=polyhedron.vertices[start],
                        end=polyhedron.vertices[end],
                        radius=edge_style.radius,
                        material=edge_material,
                    )
                    for start, end in polyhedron.edges
                )

    if styles.draw_atoms:
        primitives.extend(
            SpherePrimitive(
                atom.position,
                atom_styles[atom.key].radius,
                atom_styles[atom.key].resolved_material(styles.atom_finish),
            )
            for atom in geometry.atoms
            if atom_styles[atom.key].visible
        )
    _apply_ambient_scale(primitives, styles.ambient_scale)
    _apply_depth_shading(primitives, styles.depth_shading)
    return StyledGeometry(geometry, tuple(primitives), atom_styles)
