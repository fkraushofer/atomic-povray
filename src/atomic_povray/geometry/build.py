"""Replication, cropping, and periodic bond construction."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from itertools import product

import numpy as np
from ase.neighborlist import neighbor_list

from ..config import BondRule, DisplayBounds
from ..defaults import get_default_bonds
from ..model import (
    AtomInstance,
    AtomKey,
    Bond,
    BondNeighbor,
    GeometryModel,
    StructureModel,
)


def _make_instances(
    structure: StructureModel,
    bounds: DisplayBounds,
) -> tuple[AtomInstance, ...]:
    atoms = structure.atoms
    scaled = np.asarray(atoms.get_scaled_positions(wrap=False), dtype=float)
    cell = structure.cell
    symbols = atoms.get_chemical_symbols()
    instances: list[AtomInstance] = []

    for shift in _display_bound_image_shifts(scaled, bounds):
        shift_array = np.asarray(shift, dtype=float)
        for source_index, (symbol, fractional) in enumerate(zip(symbols, scaled)):
            displayed_fractional = fractional + shift_array
            position = displayed_fractional @ cell
            position_tuple = tuple(float(value) for value in position)
            fractional_tuple = tuple(float(value) for value in displayed_fractional)
            if bounds.contains(position_tuple, fractional_tuple):
                instances.append(
                    AtomInstance(
                        key=AtomKey(source_index, shift),
                        symbol=symbol,
                        fractional_position=fractional_tuple,
                        position=position_tuple,
                    )
                )
    return tuple(instances)


def _display_bound_image_shifts(
    scaled: np.ndarray,
    bounds: DisplayBounds,
    *,
    tolerance: float = 1e-9,
) -> tuple[tuple[int, int, int], ...]:
    """Return every lattice shift that can intersect fractional display ranges."""

    if not len(scaled):
        return ()
    shifts_by_axis: list[range] = []
    for axis, (lower, upper) in enumerate(bounds.fractional_ranges):
        minimum = float(np.min(scaled[:, axis]))
        maximum = float(np.max(scaled[:, axis]))
        first = int(np.ceil(lower - maximum - tolerance))
        last = int(np.floor(upper - minimum + tolerance))
        shifts_by_axis.append(range(first, last + 1))
    return tuple(product(*shifts_by_axis))


def _matching_rule(
    rules: Sequence[BondRule],
    symbol_a: str,
    symbol_b: str,
    distance: float,
) -> BondRule | None:
    for rule in rules:
        if rule.matches(symbol_a, symbol_b, distance):
            return rule
    return None


def _make_bonds(
    structure: StructureModel,
    primary_instances: tuple[AtomInstance, ...],
    rules: Sequence[BondRule],
    bounds: DisplayBounds,
) -> tuple[
    tuple[AtomInstance, ...],
    tuple[Bond, ...],
    tuple[tuple[BondNeighbor, ...], ...],
]:
    empty_environments = tuple(() for _ in structure.atoms)
    if not rules:
        return primary_instances, (), empty_environments

    atoms = structure.atoms
    scaled = np.asarray(atoms.get_scaled_positions(wrap=False), dtype=float)
    cell = structure.cell
    max_distance = max(rule.max_distance for rule in rules)
    indices_i, indices_j, shifts, distances = neighbor_list(
        "ijSd",
        atoms,
        cutoff=max_distance,
        self_interaction=False,
    )
    symbols = atoms.get_chemical_symbols()
    primary = {atom.key: atom for atom in primary_instances}
    all_instances = dict(primary)
    instances_by_source: dict[int, list[AtomInstance]] = {}
    for instance in primary_instances:
        instances_by_source.setdefault(instance.key.source_index, []).append(instance)
    bonds_by_endpoints: dict[tuple[AtomKey, AtomKey], Bond] = {}
    environment_lists: list[list[BondNeighbor]] = [[] for _ in atoms]

    for source_i, source_j, periodic_shift, distance in zip(
        indices_i, indices_j, shifts, distances
    ):
        source_i = int(source_i)
        source_j = int(source_j)
        distance = float(distance)
        rule = _matching_rule(
            rules,
            symbols[source_i],
            symbols[source_j],
            distance,
        )
        if rule is None:
            continue

        lattice_shift = tuple(int(value) for value in periodic_shift)
        environment_lists[source_i].append(
            BondNeighbor(
                source_index=source_j,
                image_shift=lattice_shift,
                symbol=symbols[source_j],
                rule_id=rule.rule_id,
                distance=distance,
            )
        )

        for atom_a in instances_by_source.get(source_i, ()):
            shift_b = tuple(
                atom_a.key.image_shift[axis] + lattice_shift[axis] for axis in range(3)
            )
            key_b = AtomKey(source_j, shift_b)
            key_a = atom_a.key
            if key_a == key_b:
                continue

            atom_b = primary.get(key_b)
            if atom_b is None:
                if not rule.allows_extension_from(atom_a.symbol, symbols[source_j]):
                    continue
                displayed_fractional = scaled[source_j] + np.asarray(
                    shift_b, dtype=float
                )
                position = displayed_fractional @ cell
                fractional_tuple = tuple(float(value) for value in displayed_fractional)
                position_tuple = tuple(float(value) for value in position)
                if not bounds.permits_extension(position_tuple, fractional_tuple):
                    continue
                atom_b = AtomInstance(
                    key=key_b,
                    symbol=symbols[source_j],
                    fractional_position=fractional_tuple,
                    position=position_tuple,
                    is_extension=True,
                )
                all_instances.setdefault(key_b, atom_b)

            endpoints = tuple(sorted((key_a, key_b)))
            candidate = Bond(
                atom_a=endpoints[0],
                atom_b=endpoints[1],
                rule_id=rule.rule_id,
                distance=distance,
            )
            previous = bonds_by_endpoints.get(endpoints)
            if previous is not None and previous.rule_id != candidate.rule_id:
                raise ValueError(
                    f"Bond {endpoints} matches multiple rules: "
                    f"{previous.rule_id!r} and {candidate.rule_id!r}"
                )
            bonds_by_endpoints[endpoints] = candidate

    ordered_extensions = tuple(
        all_instances[key] for key in sorted(set(all_instances).difference(primary))
    )
    instances = primary_instances + ordered_extensions
    bonds = tuple(
        sorted(
            bonds_by_endpoints.values(),
            key=lambda bond: (bond.atom_a, bond.atom_b, bond.rule_id),
        )
    )
    environments = tuple(
        tuple(
            sorted(
                items,
                key=lambda item: (
                    item.source_index,
                    item.image_shift,
                    item.rule_id,
                    item.distance,
                ),
            )
        )
        for items in environment_lists
    )
    return instances, bonds, environments


def _make_adjacency(
    instances: tuple[AtomInstance, ...],
    bonds: tuple[Bond, ...],
) -> tuple[tuple[int, ...], ...]:
    index = {atom.key: atom_index for atom_index, atom in enumerate(instances)}
    adjacency: list[list[int]] = [[] for _ in instances]
    for bond_index, bond in enumerate(bonds):
        adjacency[index[bond.atom_a]].append(bond_index)
        adjacency[index[bond.atom_b]].append(bond_index)
    return tuple(tuple(items) for items in adjacency)


def build_geometry(
    structure: StructureModel,
    *,
    bounds: DisplayBounds | None = None,
    bond_rules: Iterable[BondRule] | None = None,
) -> GeometryModel:
    """Build geometry and complete source environments from matching bond rules.

    When ``bond_rules`` is omitted, editable ASE-backed defaults are generated
    for the elements in ``structure``. Pass an empty iterable to disable bonds
    explicitly.
    """

    bounds = bounds or DisplayBounds()
    rules = tuple(
        get_default_bonds(structure, print_table=False)
        if bond_rules is None
        else bond_rules
    )
    primary_instances = _make_instances(structure, bounds)
    instances, bonds, environments = _make_bonds(
        structure,
        primary_instances,
        rules,
        bounds,
    )
    adjacency = _make_adjacency(instances, bonds)
    return GeometryModel(structure, instances, bonds, adjacency, environments)
