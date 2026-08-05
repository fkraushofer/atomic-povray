"""ASE-backed element defaults and editable geometry rules."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import replace
from itertools import combinations_with_replacement
from math import isfinite
from typing import Any

from ase.data import atomic_numbers, covalent_radii
from ase.data.colors import jmol_colors

from .config import BondRule, CoordinationPolyhedronRule
from .model import StructureModel
from .primitives import Color
from .profile import DEFAULT_PROFILE, AtomicPovrayProfile


DEFAULT_HYDROGEN_BOND_RULE_ID = "default:hydrogen:O-H"

# Candidate pairs follow the broad chemical policy used by VESTA without
# redistributing its style.ini table: noble gases and metal-metal pairs are
# omitted, while common non-metals and metalloids may bond to one another or
# to metals.
_NOBLE_GASES = frozenset({"He", "Ne", "Ar", "Kr", "Xe", "Rn", "Og"})
_METALLOIDS = frozenset({"B", "Si", "Ge", "As", "Sb", "Te"})
_NONMETALS = frozenset(
    {
        "H",
        "C",
        "N",
        "O",
        "F",
        "P",
        "S",
        "Se",
        "Cl",
        "Br",
        "I",
        "At",
        "Ts",
    }
)
_NONMETAL_LIKE = _METALLOIDS | _NONMETALS


def default_atom_radius(symbol: str) -> float:
    """Return ASE's Cordero covalent radius for an element."""

    return float(covalent_radii[_atomic_number(symbol)])


def default_atom_color(symbol: str) -> Color:
    """Return ASE's Jmol color for an element."""

    red, green, blue = jmol_colors[_atomic_number(symbol)]
    return Color(float(red), float(green), float(blue))


class BondRuleSet:
    """An ordered, editable collection of uniquely named bond rules."""

    def __init__(self, rules: Iterable[BondRule] = ()) -> None:
        self._rules: dict[str, BondRule] = {}
        for rule in rules:
            self.add(rule)

    def __iter__(self) -> Iterator[BondRule]:
        return iter(self._rules.values())

    def __len__(self) -> int:
        return len(self._rules)

    def __getitem__(self, key: int | slice | str) -> BondRule | tuple[BondRule, ...]:
        if isinstance(key, str):
            return self._rules[key]
        return tuple(self._rules.values())[key]

    def __contains__(self, rule_id: object) -> bool:
        return rule_id in self._rules

    def __repr__(self) -> str:
        return f"{type(self).__name__}({list(self._rules.values())!r})"

    def add(self, rule: BondRule) -> None:
        """Append a rule, rejecting duplicate rule IDs."""

        if not isinstance(rule, BondRule):
            raise TypeError("rule must be a BondRule")
        if rule.rule_id in self._rules:
            raise ValueError(f"Duplicate bond rule ID: {rule.rule_id!r}")
        self._rules[rule.rule_id] = rule

    def remove(self, rule_id: str) -> BondRule:
        """Remove and return one rule by ID."""

        try:
            return self._rules.pop(rule_id)
        except KeyError:
            raise KeyError(f"Unknown bond rule ID: {rule_id!r}") from None

    def update(self, rule_id: str, **changes: Any) -> BondRule:
        """Replace fields of one rule while preserving collection order."""

        try:
            updated = replace(self._rules[rule_id], **changes)
        except KeyError:
            raise KeyError(f"Unknown bond rule ID: {rule_id!r}") from None
        if updated.rule_id != rule_id and updated.rule_id in self._rules:
            raise ValueError(f"Duplicate bond rule ID: {updated.rule_id!r}")

        self._rules = {
            (updated.rule_id if key == rule_id else key): (
                updated if key == rule_id else rule
            )
            for key, rule in self._rules.items()
        }
        return updated

    def remove_pair(self, element_a: str, element_b: str) -> tuple[BondRule, ...]:
        """Remove and return every rule for an unordered element pair."""

        pair = frozenset((element_a, element_b))
        removed = tuple(
            rule
            for rule in self._rules.values()
            if frozenset((rule.element_a, rule.element_b)) == pair
        )
        for rule in removed:
            del self._rules[rule.rule_id]
        return removed

    def clear(self) -> None:
        self._rules.clear()

    def format_table(self) -> str:
        """Return a plain-text summary of the current bond rules."""

        headers = ("Rule", "Pair", "Min (Å)", "Max (Å)", "Boundary extension")
        rows = [
            (
                rule.rule_id,
                f"{rule.element_a}-{rule.element_b}",
                f"{rule.min_distance:.3f}",
                f"{rule.max_distance:.3f}",
                _extension_description(rule),
            )
            for rule in self._rules.values()
        ]
        widths = [
            max([len(header), *(len(row[index]) for row in rows)])
            for index, header in enumerate(headers)
        ]

        def format_row(row: tuple[str, ...]) -> str:
            return " | ".join(
                value.ljust(width) for value, width in zip(row, widths)
            )

        separator = "-+-".join("-" * width for width in widths)
        return "\n".join(
            (format_row(headers), separator, *(format_row(row) for row in rows))
        )

    def print_table(self) -> None:
        """Print a plain-text summary of the current bond rules."""

        print(self.format_table())


class PolyhedronRuleSet:
    """An ordered, editable collection of uniquely named polyhedron rules."""

    def __init__(
        self, rules: Iterable[CoordinationPolyhedronRule] = ()
    ) -> None:
        self._rules: dict[str, CoordinationPolyhedronRule] = {}
        for rule in rules:
            self.add(rule)

    def __iter__(self) -> Iterator[CoordinationPolyhedronRule]:
        return iter(self._rules.values())

    def __len__(self) -> int:
        return len(self._rules)

    def __getitem__(
        self, key: int | slice | str
    ) -> CoordinationPolyhedronRule | tuple[CoordinationPolyhedronRule, ...]:
        if isinstance(key, str):
            return self._rules[key]
        return tuple(self._rules.values())[key]

    def __contains__(self, rule_id: object) -> bool:
        return rule_id in self._rules

    def __repr__(self) -> str:
        return f"{type(self).__name__}({list(self._rules.values())!r})"

    def add(self, rule: CoordinationPolyhedronRule) -> None:
        """Append a rule, rejecting duplicate rule IDs."""

        if not isinstance(rule, CoordinationPolyhedronRule):
            raise TypeError("rule must be a CoordinationPolyhedronRule")
        if rule.rule_id in self._rules:
            raise ValueError(f"Duplicate polyhedron rule ID: {rule.rule_id!r}")
        self._rules[rule.rule_id] = rule

    def remove(self, rule_id: str) -> CoordinationPolyhedronRule:
        """Remove and return one rule by ID."""

        try:
            return self._rules.pop(rule_id)
        except KeyError:
            raise KeyError(f"Unknown polyhedron rule ID: {rule_id!r}") from None

    def update(
        self, rule_id: str, **changes: Any
    ) -> CoordinationPolyhedronRule:
        """Replace fields of one rule while preserving collection order."""

        try:
            updated = replace(self._rules[rule_id], **changes)
        except KeyError:
            raise KeyError(f"Unknown polyhedron rule ID: {rule_id!r}") from None
        if updated.rule_id != rule_id and updated.rule_id in self._rules:
            raise ValueError(f"Duplicate polyhedron rule ID: {updated.rule_id!r}")

        self._rules = {
            (updated.rule_id if key == rule_id else key): (
                updated if key == rule_id else rule
            )
            for key, rule in self._rules.items()
        }
        return updated

    def clear(self) -> None:
        self._rules.clear()

    def format_table(self) -> str:
        """Return a plain-text summary of the current polyhedron rules."""

        headers = ("Rule", "Center", "Ligands", "Bond rules", "Boundary")
        rows = [
            (
                rule.rule_id,
                rule.center_element,
                _format_filter(rule.ligand_elements),
                _format_filter(rule.bond_rules),
                rule.boundary_mode,
            )
            for rule in self._rules.values()
        ]
        widths = [
            max([len(header), *(len(row[index]) for row in rows)])
            for index, header in enumerate(headers)
        ]

        def format_row(row: tuple[str, ...]) -> str:
            return " | ".join(
                value.ljust(width) for value, width in zip(row, widths)
            )

        separator = "-+-".join("-" * width for width in widths)
        return "\n".join(
            (format_row(headers), separator, *(format_row(row) for row in rows))
        )

    def print_table(self) -> None:
        """Print a plain-text summary of the current polyhedron rules."""

        print(self.format_table())


def get_default_bonds(
    structure: StructureModel | Any,
    *,
    bond_scale: float | None = None,
    include_pairs: Iterable[tuple[str, str]] = (),
    exclude_pairs: Iterable[tuple[str, str]] = (),
    print_table: bool = True,
    profile: AtomicPovrayProfile = DEFAULT_PROFILE,
) -> BondRuleSet:
    """Materialize editable default rules for the elements in a structure.

    Ordinary maximum distances are ``bond_scale`` times the summed ASE
    covalent radii. Candidate pairs exclude noble gases and metal-metal pairs
    unless explicitly included. If O and H are present, a separate hydrogen
    bond rule extends from the covalent cutoff to a fixed 2.1 Å and never
    searches beyond display boundaries. By default, the materialized rules are
    printed as a compact table; pass ``print_table=False`` to suppress it.
    """

    if bond_scale is None:
        bond_scale = profile.geometry.bond_scale
    hydrogen_bond_max = profile.geometry.hydrogen_bond_max
    if not isfinite(bond_scale) or bond_scale <= 0:
        raise ValueError("bond_scale must be positive and finite")

    atoms = structure.atoms if isinstance(structure, StructureModel) else structure
    try:
        symbols = frozenset(atoms.get_chemical_symbols())
    except AttributeError:
        raise TypeError("structure must be an ASE Atoms or StructureModel") from None
    for symbol in symbols:
        _atomic_number(symbol)

    included = _normalize_pairs(include_pairs)
    excluded = _normalize_pairs(exclude_pairs)
    present_pairs = {
        frozenset(pair)
        for pair in combinations_with_replacement(
            sorted(symbols, key=_atomic_number),
            2,
        )
    }

    selected_pairs = {
        pair
        for pair in present_pairs
        if _is_default_candidate(pair) or pair in included
    }
    selected_pairs.difference_update(excluded)

    rules = BondRuleSet()
    for pair in sorted(selected_pairs, key=_pair_sort_key):
        element_a, element_b = _orient_pair(pair)
        maximum = bond_scale * (
            default_atom_radius(element_a) + default_atom_radius(element_b)
        )
        is_oh = pair == frozenset(("O", "H"))
        rules.add(
            BondRule(
                element_a,
                element_b,
                0.0,
                maximum,
                name=(
                    "default:covalent:O-H"
                    if is_oh
                    else f"default:{element_a}-{element_b}"
                ),
            )
        )
        if is_oh:
            if maximum >= hydrogen_bond_max:
                raise ValueError(
                    "bond_scale makes the covalent O-H cutoff reach or exceed "
                    f"the fixed {hydrogen_bond_max} Å hydrogen-bond limit"
                )
            rules.add(
                BondRule(
                    "O",
                    "H",
                    maximum,
                    hydrogen_bond_max,
                    name=DEFAULT_HYDROGEN_BOND_RULE_ID,
                    extension_mode="none",
                )
            )
    if print_table:
        rules.print_table()
    return rules


def get_default_polyhedra(
    bond_rules: Iterable[BondRule],
    *,
    include_centers: Iterable[str] = (),
    exclude_centers: Iterable[str] = (),
    print_table: bool = True,
) -> PolyhedronRuleSet:
    """Infer editable metal-centered polyhedron rules from finalized bonds.

    A center is inferred when it is the first endpoint of an asymmetric
    metal-to-nonmetal bond rule. Each generated polyhedron uses every bond
    around that center, so additional ligand types are included automatically.
    Metalloids and nonmetals can be requested explicitly with
    ``include_centers``.
    """

    included = _normalize_elements(include_centers)
    excluded = _normalize_elements(exclude_centers)
    inferred = {
        rule.element_a
        for rule in bond_rules
        if rule.extension_mode == "asymmetric"
        and rule.element_a not in _NONMETAL_LIKE
        and rule.element_a not in _NOBLE_GASES
        and rule.element_b in _NONMETAL_LIKE
    }
    centers = (inferred | included) - excluded
    rules = PolyhedronRuleSet(
        CoordinationPolyhedronRule(
            center_element=center,
            name=f"default:{center}-polyhedron",
            boundary_mode="complete",
            on_degenerate="ignore",
        )
        for center in sorted(centers, key=_atomic_number)
    )
    if print_table:
        rules.print_table()
    return rules


def _extension_description(rule: BondRule) -> str:
    if rule.extension_mode == "none":
        return "none"
    if rule.extension_mode == "symmetric" or rule.element_a == rule.element_b:
        return f"{rule.element_a} ↔ {rule.element_b}"
    return f"{rule.element_a} → {rule.element_b}"


def _atomic_number(symbol: str) -> int:
    try:
        return atomic_numbers[symbol]
    except (KeyError, TypeError):
        raise ValueError(f"Unknown chemical element: {symbol!r}") from None


def _normalize_pairs(
    pairs: Iterable[tuple[str, str]],
) -> frozenset[frozenset[str]]:
    normalized: set[frozenset[str]] = set()
    for pair in pairs:
        if len(pair) != 2:
            raise ValueError("Element pairs must contain exactly two symbols")
        element_a, element_b = pair
        _atomic_number(element_a)
        _atomic_number(element_b)
        normalized.add(frozenset(pair))
    return frozenset(normalized)


def _normalize_elements(elements: Iterable[str]) -> frozenset[str]:
    normalized = frozenset(elements)
    for element in normalized:
        _atomic_number(element)
    return normalized


def _format_filter(values: frozenset[str] | None) -> str:
    return "all" if values is None else ", ".join(sorted(values))


def _is_default_candidate(pair: frozenset[str]) -> bool:
    if pair & _NOBLE_GASES:
        return False
    return bool(pair & _NONMETAL_LIKE)


def _orient_pair(pair: frozenset[str]) -> tuple[str, str]:
    elements = sorted(pair, key=_atomic_number)
    if len(elements) == 1:
        return elements[0], elements[0]

    element_a, element_b = elements
    a_nonmetal = element_a in _NONMETAL_LIKE
    b_nonmetal = element_b in _NONMETAL_LIKE
    if a_nonmetal != b_nonmetal:
        return (element_b, element_a) if a_nonmetal else (element_a, element_b)
    if element_a == "H":
        return element_b, element_a
    if element_b == "H":
        return element_a, element_b
    if element_a in _METALLOIDS and element_b not in _METALLOIDS:
        return element_a, element_b
    if element_b in _METALLOIDS and element_a not in _METALLOIDS:
        return element_b, element_a
    return element_a, element_b


def _pair_sort_key(pair: frozenset[str]) -> tuple[int, int]:
    numbers = sorted(_atomic_number(symbol) for symbol in pair)
    if len(numbers) == 1:
        numbers.append(numbers[0])
    return numbers[0], numbers[1]
