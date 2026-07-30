"""Replication, cropping, and periodic bond construction."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from itertools import product

import numpy as np
from ase.neighborlist import neighbor_list

from ..config import (
    BondRule,
    BoundarySet,
    CartesianBounds,
    ReplicationConfig,
)
from ..model import AtomInstance, AtomKey, Bond, GeometryModel, StructureModel


def _centered_indices(count: int) -> range:
    if count < 1:
        raise ValueError("Every repetition count must be at least one")
    return range(-(count // 2), count - count // 2)


def centered_image_shifts(
    repetitions: tuple[int, int, int],
) -> tuple[tuple[int, int, int], ...]:
    """Return legacy-compatible centered lattice shifts.

    Examples: ``1 -> (0,)``, ``2 -> (-1, 0)``, ``3 -> (-1, 0, 1)``.
    """

    if len(repetitions) != 3:
        raise ValueError("repetitions must contain exactly three integers")
    return tuple(product(*(_centered_indices(int(count)) for count in repetitions)))


def _make_instances(
    structure: StructureModel,
    replication: ReplicationConfig,
    bounds: BoundarySet | CartesianBounds,
) -> tuple[AtomInstance, ...]:
    atoms = structure.atoms
    scaled = np.asarray(atoms.get_scaled_positions(wrap=False), dtype=float)
    cell = structure.cell
    symbols = atoms.get_chemical_symbols()
    instances: list[AtomInstance] = []

    for shift in centered_image_shifts(replication.counts):
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
    replication: ReplicationConfig,
    bounds: BoundarySet | CartesianBounds,
) -> tuple[tuple[AtomInstance, ...], tuple[Bond, ...]]:
    if not rules or not primary_instances:
        return primary_instances, ()

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

    for source_i, source_j, periodic_shift, distance in zip(
        indices_i, indices_j, shifts, distances
    ):
        rule = _matching_rule(
            rules,
            symbols[int(source_i)],
            symbols[int(source_j)],
            float(distance),
        )
        if rule is None:
            continue

        lattice_shift = tuple(int(value) for value in periodic_shift)
        for atom_a in instances_by_source.get(int(source_i), ()):
            shift_b = tuple(
                atom_a.key.image_shift[axis] + lattice_shift[axis] for axis in range(3)
            )
            key_b = AtomKey(int(source_j), shift_b)
            key_a = atom_a.key
            if key_a == key_b:
                continue

            atom_b = primary.get(key_b)
            if atom_b is None:
                if not rule.allows_extension_from(
                    atom_a.symbol, symbols[int(source_j)]
                ):
                    continue
                displayed_fractional = scaled[int(source_j)] + np.asarray(
                    shift_b, dtype=float
                )
                position = displayed_fractional @ cell
                fractional_tuple = tuple(float(value) for value in displayed_fractional)
                position_tuple = tuple(float(value) for value in position)
                if not _replication_permits_extension(shift_b, replication):
                    continue
                if not bounds.permits_extension(position_tuple, fractional_tuple):
                    continue
                atom_b = AtomInstance(
                    key=key_b,
                    symbol=symbols[int(source_j)],
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
                distance=float(distance),
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
    return instances, bonds


def _replication_permits_extension(
    image_shift: tuple[int, int, int],
    replication: ReplicationConfig,
) -> bool:
    shifts_by_axis = tuple(
        _centered_indices(int(count)) for count in replication.counts
    )
    for axis, (shift, valid) in enumerate(zip(image_shift, shifts_by_axis)):
        if shift < valid.start and not replication.lower_allow_bond_extensions[axis]:
            return False
        if shift >= valid.stop and not replication.upper_allow_bond_extensions[axis]:
            return False
    return True


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
    repetitions: tuple[int, int, int] | ReplicationConfig = (1, 1, 1),
    bounds: BoundarySet | CartesianBounds | None = None,
    bond_rules: Iterable[BondRule] = (),
) -> GeometryModel:
    """Build the reusable structural geometry stage."""

    bounds = bounds or BoundarySet()
    replication = (
        repetitions
        if isinstance(repetitions, ReplicationConfig)
        else ReplicationConfig(tuple(int(value) for value in repetitions))
    )
    rules = tuple(bond_rules)
    primary_instances = _make_instances(structure, replication, bounds)
    instances, bonds = _make_bonds(
        structure, primary_instances, rules, replication, bounds
    )
    adjacency = _make_adjacency(instances, bonds)
    return GeometryModel(structure, instances, bonds, adjacency)
