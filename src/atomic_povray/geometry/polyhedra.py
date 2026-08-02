"""Coordination-polyhedron construction from complete bond environments."""

from __future__ import annotations

from collections.abc import Sequence
from math import cos
from warnings import warn

import numpy as np
from scipy.spatial import ConvexHull

from ..config import CoordinationPolyhedronRule
from ..model import (
    AtomInstance,
    AtomKey,
    BondNeighbor,
    CoordinationPolyhedron,
    StructureModel,
)


def _selected_indices(rule: CoordinationPolyhedronRule, structure: StructureModel) -> frozenset[int] | None:
    if rule.center_selector is None:
        return None
    selection = rule.center_selector(structure.atoms)
    if isinstance(selection, (int, np.integer)) and not isinstance(selection, bool):
        values = np.asarray([selection])
    else:
        values = np.asarray(selection)
    count = len(structure.atoms)
    if values.dtype.kind == "b":
        if values.shape != (count,):
            raise ValueError(
                f"Boolean center selector masks must have shape ({count},), got {values.shape}"
            )
        return frozenset(int(index) for index in np.flatnonzero(values))
    if values.size == 0:
        return frozenset()
    if values.ndim != 1 or values.dtype.kind not in "iu":
        raise TypeError(
            "Center selectors must return an integer index, a one-dimensional "
            "integer sequence, or a one-dimensional Boolean mask"
        )
    if np.any(values < 0) or np.any(values >= count):
        raise IndexError(f"Center selector indices must lie between 0 and {count - 1}")
    return frozenset(int(value) for value in values)


def _unique_ligands(
    center: AtomInstance,
    neighbors: Sequence[BondNeighbor],
    structure: StructureModel,
    rule: CoordinationPolyhedronRule,
    visible_keys: frozenset[AtomKey],
) -> tuple[tuple[AtomKey, ...], np.ndarray]:
    scaled = np.asarray(structure.atoms.get_scaled_positions(wrap=False), dtype=float)
    cell = structure.cell
    keys: list[AtomKey] = []
    positions: list[np.ndarray] = []
    for neighbor in neighbors:
        if (
            rule.ligand_elements is not None
            and neighbor.symbol not in rule.ligand_elements
        ):
            continue
        if rule.bond_rules is not None and neighbor.rule_id not in rule.bond_rules:
            continue
        shift = tuple(
            center.key.image_shift[axis] + neighbor.image_shift[axis]
            for axis in range(3)
        )
        key = AtomKey(neighbor.source_index, shift)
        if rule.boundary_mode == "visible" and key not in visible_keys:
            continue
        position = (scaled[neighbor.source_index] + np.asarray(shift)) @ cell
        if any(
            np.linalg.norm(position - previous) <= rule.position_tolerance
            for previous in positions
        ):
            continue
        keys.append(key)
        positions.append(position)
    if not positions:
        return (), np.empty((0, 3), dtype=float)
    vertices = np.asarray(positions, dtype=float)
    if rule.expansion:
        center_position = np.asarray(center.position, dtype=float)
        vectors = vertices - center_position
        lengths = np.linalg.norm(vectors, axis=1)
        if np.any(lengths <= rule.position_tolerance):
            raise ValueError(
                f"Polyhedron {rule.rule_id!r} has a ligand at its center"
            )
        vertices = vertices + rule.expansion * vectors / lengths[:, None]
    return tuple(keys), vertices


def _planar_hull(vertices: np.ndarray) -> tuple[
    tuple[tuple[int, int, int], ...], tuple[tuple[int, int], ...]
]:
    centered = vertices - np.mean(vertices, axis=0)
    _, _, vh = np.linalg.svd(centered, full_matrices=False)
    projected = centered @ vh[:2].T
    hull = ConvexHull(projected)
    perimeter = tuple(int(index) for index in hull.vertices)
    faces = tuple(
        (perimeter[0], perimeter[index], perimeter[index + 1])
        for index in range(1, len(perimeter) - 1)
    )
    edges = tuple(
        tuple(sorted((perimeter[index], perimeter[(index + 1) % len(perimeter)])))
        for index in range(len(perimeter))
    )
    return faces, tuple(sorted(edges))


def _spatial_hull(
    vertices: np.ndarray,
    angle_tolerance: float,
) -> tuple[tuple[tuple[int, int, int], ...], tuple[tuple[int, int], ...]]:
    hull = ConvexHull(vertices)
    interior = np.mean(vertices[hull.vertices], axis=0)
    faces: list[tuple[int, int, int]] = []
    edge_facets: dict[tuple[int, int], list[int]] = {}
    for facet_index, simplex in enumerate(hull.simplices):
        face = [int(value) for value in simplex]
        a, b, c = vertices[face]
        if np.dot(np.cross(b - a, c - a), np.mean((a, b, c), axis=0) - interior) < 0:
            face[1], face[2] = face[2], face[1]
        faces.append(tuple(face))
        for start, end in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            edge_facets.setdefault(tuple(sorted((start, end))), []).append(facet_index)

    threshold = cos(angle_tolerance)
    edges = []
    for edge, facets in edge_facets.items():
        if len(facets) != 2:
            edges.append(edge)
            continue
        normal_a = hull.equations[facets[0], :3]
        normal_b = hull.equations[facets[1], :3]
        normal_a /= np.linalg.norm(normal_a)
        normal_b /= np.linalg.norm(normal_b)
        if abs(float(np.dot(normal_a, normal_b))) < threshold:
            edges.append(edge)
    return tuple(faces), tuple(sorted(edges))


def _hull(
    vertices: np.ndarray,
    rule: CoordinationPolyhedronRule,
) -> tuple[tuple[tuple[int, int, int], ...], tuple[tuple[int, int], ...], int] | None:
    if len(vertices) < 3:
        return None
    centered = vertices - np.mean(vertices, axis=0)
    singular_values = np.linalg.svd(centered, compute_uv=False)
    scale = singular_values[0] if len(singular_values) else 0.0
    rank = int(np.sum(singular_values > rule.rank_tolerance * max(scale, 1.0)))
    if rank == 2:
        faces, edges = _planar_hull(vertices)
        return faces, edges, 2
    if rank == 3 and len(vertices) >= 4:
        faces, edges = _spatial_hull(vertices, rule.coplanar_angle_tolerance)
        return faces, edges, 3
    return None


def _handle_degenerate(rule: CoordinationPolyhedronRule, center: AtomKey) -> None:
    message = (
        f"Skipping degenerate coordination polyhedron {rule.rule_id!r} "
        f"around atom {center}"
    )
    if rule.on_degenerate == "error":
        raise ValueError(message)
    if rule.on_degenerate == "warn":
        warn(message, stacklevel=3)


def make_polyhedra(
    structure: StructureModel,
    primary_instances: tuple[AtomInstance, ...],
    instances: tuple[AtomInstance, ...],
    environments: tuple[tuple[BondNeighbor, ...], ...],
    rules: tuple[CoordinationPolyhedronRule, ...],
) -> tuple[CoordinationPolyhedron, ...]:
    """Build polyhedra only around in-bounds (primary) central atoms."""

    visible_keys = frozenset(atom.key for atom in instances)
    symbols = structure.atoms.get_chemical_symbols()
    result: list[CoordinationPolyhedron] = []
    for rule in rules:
        selected = _selected_indices(rule, structure)
        for center in primary_instances:
            source_index = center.key.source_index
            if symbols[source_index] != rule.center_element:
                continue
            if selected is not None and source_index not in selected:
                continue
            ligand_keys, vertices = _unique_ligands(
                center,
                environments[source_index],
                structure,
                rule,
                visible_keys,
            )
            hull = _hull(vertices, rule)
            if hull is None:
                _handle_degenerate(rule, center.key)
                continue
            faces, edges, dimension = hull
            result.append(
                CoordinationPolyhedron(
                    center=center.key,
                    rule_id=rule.rule_id,
                    ligand_keys=ligand_keys,
                    vertices=tuple(tuple(float(value) for value in row) for row in vertices),
                    faces=faces,
                    edges=edges,
                    dimension=dimension,
                )
            )
    return tuple(result)
