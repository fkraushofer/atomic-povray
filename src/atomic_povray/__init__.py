"""Public, notebook-friendly API for atomic-povray Prototype 1."""

from .backends import (
    RenderConfig,
    RenderResult,
    render_scene,
    scene_to_sdl,
    write_scene,
)
from .config import (
    BondRule,
    BoundaryPlane,
    BoundarySet,
    CartesianBounds,
    ReplicationConfig,
)
from .geometry import build_geometry, centered_image_shifts
from .io import load_structure
from .model import AtomInstance, AtomKey, Bond, GeometryModel, StructureModel
from .primitives import (
    Color,
    CylinderPrimitive,
    Finish,
    Material,
    Primitive,
    SpherePrimitive,
    TriangleMeshPrimitive,
)
from .scene import AreaLight, Background, Camera, PointLight, Scene, make_scene
from .styling import AtomStyle, BondStyle, StyleConfig, StyledGeometry, apply_styles

__all__ = [
    "AreaLight",
    "AtomInstance",
    "AtomKey",
    "AtomStyle",
    "Background",
    "Bond",
    "BondRule",
    "BondStyle",
    "BoundaryPlane",
    "BoundarySet",
    "Camera",
    "CartesianBounds",
    "Color",
    "CylinderPrimitive",
    "Finish",
    "GeometryModel",
    "Material",
    "PointLight",
    "Primitive",
    "RenderConfig",
    "RenderResult",
    "ReplicationConfig",
    "Scene",
    "SpherePrimitive",
    "StructureModel",
    "StyleConfig",
    "StyledGeometry",
    "TriangleMeshPrimitive",
    "apply_styles",
    "build_geometry",
    "centered_image_shifts",
    "load_structure",
    "make_scene",
    "render_scene",
    "scene_to_sdl",
    "write_scene",
]
