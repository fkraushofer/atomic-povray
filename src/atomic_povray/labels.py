"""Helpers for adding temporary atom labels to a styled scene."""

from __future__ import annotations

from math import isfinite
from numbers import Real
from typing import Callable

import numpy as np
from ase import Atoms

from .model import AtomInstance, Vec3
from .primitives import Color, Finish, Material, TextPrimitive
from .scene import Camera
from .styling import StyledGeometry

AtomLabeler = Callable[[AtomInstance], str]
AtomLabelSelection = Callable[[AtomInstance], bool]


def element_labels(atoms: Atoms) -> tuple[str, ...]:
    """Return VESTA-style labels numbered separately for each element.

    Numbering follows the ASE atom order, including when atoms of the same
    element are not contiguous. For example, ``O Fe O Fe`` becomes
    ``O1 Fe1 O2 Fe2``.
    """

    counts: dict[str, int] = {}
    labels: list[str] = []
    for symbol in atoms.get_chemical_symbols():
        counts[symbol] = counts.get(symbol, 0) + 1
        labels.append(f"{symbol}{counts[symbol]}")
    return tuple(labels)


def _camera_basis(camera: Camera) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return unit vectors for image-right, image-up, and toward-camera."""

    view = np.asarray(camera.direction, dtype=float)
    view_length = float(np.linalg.norm(view))
    if not isfinite(view_length) or view_length <= 0:
        raise ValueError("camera direction must be non-zero and finite")
    view /= view_length

    up_hint = np.asarray(camera.up, dtype=float)
    right = np.cross(view, up_hint)
    right_length = float(np.linalg.norm(right))
    if not isfinite(right_length) or right_length <= 0:
        raise ValueError("camera up must be finite and not parallel to direction")
    right /= right_length

    up = np.cross(right, view)
    up /= np.linalg.norm(up)
    toward_camera = -view
    return right, up, toward_camera


def _positive_finite(name: str, value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    value = float(value)
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return value


def label_atoms(
    styled: StyledGeometry,
    *,
    camera: Camera,
    labels: AtomLabeler | None = None,
    selection: AtomLabelSelection | None = None,
    offset: Vec3 = (0.0, 0.0, 0.0),
    size: float = 0.4,
    thickness: float = 0.02,
    font: str = "timrom.ttf",
    color: Color = Color(0.0, 0.0, 0.0),
    material: Material | None = None,
) -> tuple[TextPrimitive, ...]:
    """Create camera-facing labels for visible atoms in the styled geometry.

    The offset is expressed in camera-relative coordinates: image-right,
    image-up, and toward-camera. The same offset is applied to every label.
    Labels are first moved from each atom center to its visible surface using
    the final resolved atom radius.
    """

    size = _positive_finite("size", size)
    thickness = _positive_finite("thickness", thickness)
    if not font:
        raise ValueError("font must not be empty")
    if len(offset) != 3 or not all(isfinite(float(value)) for value in offset):
        raise ValueError("offset must contain three finite values")
    if not styled.atom_styles:
        raise ValueError(
            "StyledGeometry has no resolved atom styles; create it with apply_styles()"
        )

    right, up, toward_camera = _camera_basis(camera)
    offset_vector = (
        float(offset[0]) * right
        + float(offset[1]) * up
        + float(offset[2]) * toward_camera
    )
    if labels is None:
        labels_by_source = element_labels(styled.geometry.structure.atoms)

        def labeler(atom: AtomInstance) -> str:
            return labels_by_source[atom.key.source_index]
    else:
        labeler = labels
    text_material = material or Finish().material(color)

    primitives: list[TextPrimitive] = []
    for atom in styled.geometry.atoms:
        atom_style = styled.atom_styles.get(atom.key)
        if atom_style is None or not atom_style.visible:
            continue
        if selection is not None and not selection(atom):
            continue

        text = str(labeler(atom))
        if not text:
            continue
        position = (
            np.asarray(atom.position, dtype=float)
            + atom_style.radius * toward_camera
            + offset_vector
        )
        primitives.append(
            TextPrimitive(
                text=text,
                position=tuple(float(value) for value in position),
                right=tuple(float(value) for value in right),
                up=tuple(float(value) for value in up),
                normal=tuple(float(value) for value in toward_camera),
                material=text_material,
                font=font,
                size=size,
                thickness=thickness,
            )
        )
    return tuple(primitives)
