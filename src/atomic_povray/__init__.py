"""Public, notebook-friendly API for atomic-povray Prototype 1."""

from .backends import (
    RenderConfig,
    RenderResult,
    render_scene,
    scene_to_sdl,
    write_ini,
    write_scene,
)
from .config import (
    BondRule,
    CutoffPlane,
    DisplayBounds,
)
from .geometry import build_geometry
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
from .scene import AreaLight, Background, Camera, Fog, PointLight, Scene, make_scene
from .styling import (
    AtomStyle,
    BondStyle,
    DepthShading,
    StyleConfig,
    StyledGeometry,
    apply_styles,
)

__all__ = [
    "AreaLight",
    "AtomInstance",
    "AtomKey",
    "AtomStyle",
    "Background",
    "Bond",
    "BondRule",
    "BondStyle",
    "Camera",
    "Color",
    "CutoffPlane",
    "CylinderPrimitive",
    "DepthShading",
    "DisplayBounds",
    "Finish",
    "Fog",
    "GeometryModel",
    "Material",
    "PointLight",
    "Primitive",
    "RenderConfig",
    "RenderResult",
    "Scene",
    "SpherePrimitive",
    "StructureModel",
    "StyleConfig",
    "StyledGeometry",
    "TriangleMeshPrimitive",
    "apply_styles",
    "build_geometry",
    "load_structure",
    "make_scene",
    "render_scene",
    "scene_to_sdl",
    "write_ini",
    "write_scene",
]
