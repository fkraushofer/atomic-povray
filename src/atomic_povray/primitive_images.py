"""Periodic replication helpers for renderer-independent primitives."""

from __future__ import annotations

from dataclasses import replace
from itertools import product
from numbers import Integral

import numpy as np

from .model import StructureModel, Vec3
from .primitives import (
    CylinderPrimitive,
    Primitive,
    SpherePrimitive,
    TextPrimitive,
    TriangleMeshPrimitive,
)

ImageRanges = tuple[tuple[int, int], tuple[int, int], tuple[int, int]]


def primitive_images(
    primitive: Primitive,
    structure: StructureModel,
    ranges: ImageRanges,
) -> tuple[Primitive, ...]:
    """Return lattice-translated copies of a primitive.

    ``ranges`` contains three half-open integer ``(minimum, maximum)`` pairs,
    using the same lattice-vector order and sign convention as
    :attr:`DisplayBounds.fractional_ranges`. Each image is translated by
    ``i * a + j * b + k * c`` using the ASE cell in ``structure``.
    """

    image_ranges = _validate_image_ranges(ranges)
    cell = structure.cell
    return tuple(
        _translate_primitive(primitive, tuple(np.asarray(image) @ cell))
        for image in product(*(range(lower, upper) for lower, upper in image_ranges))
    )


def _validate_image_ranges(ranges: ImageRanges) -> ImageRanges:
    if len(ranges) != 3:
        raise ValueError("ranges must contain three (min, max) pairs")

    validated: list[tuple[int, int]] = []
    for limits in ranges:
        if len(limits) != 2:
            raise ValueError("ranges must contain three (min, max) pairs")
        lower, upper = limits
        if any(isinstance(value, bool) or not isinstance(value, Integral) for value in limits):
            raise TypeError("range endpoints must be integers")
        if lower > upper:
            raise ValueError("range minimum must not exceed its maximum")
        validated.append((int(lower), int(upper)))
    return tuple(validated)  # type: ignore[return-value]


def _translate_point(point: Vec3, shift: Vec3) -> Vec3:
    return tuple(float(coordinate + offset) for coordinate, offset in zip(point, shift))


def _translate_primitive(primitive: Primitive, shift: Vec3) -> Primitive:
    if isinstance(primitive, SpherePrimitive):
        return replace(primitive, center=_translate_point(primitive.center, shift))
    if isinstance(primitive, CylinderPrimitive):
        return replace(
            primitive,
            start=_translate_point(primitive.start, shift),
            end=_translate_point(primitive.end, shift),
        )
    if isinstance(primitive, TextPrimitive):
        return replace(primitive, position=_translate_point(primitive.position, shift))
    if isinstance(primitive, TriangleMeshPrimitive):
        return replace(
            primitive,
            vertices=tuple(_translate_point(vertex, shift) for vertex in primitive.vertices),
            reference_position=(
                None
                if primitive.reference_position is None
                else _translate_point(primitive.reference_position, shift)
            ),
        )
    raise TypeError(f"Unsupported primitive type: {type(primitive).__name__}")
