"""Canonical shipped defaults for atomic-povray.

This private module centralizes choices that users may reasonably want to
replace for all figures.  Public, composable defaults profiles will build on
these values in a separate change.
"""

from __future__ import annotations

from types import MappingProxyType

from .primitives import Color, Finish


# Geometry and bond inference.
DEFAULT_BOND_SCALE = 1.2
DEFAULT_HYDROGEN_BOND_MAX = 2.1

# Styling and representation presets.
DEFAULT_PRESET_STYLE = "ball_and_stick"
DEFAULT_PRESET_ATOM_SIZE_SCALES = MappingProxyType(
    {
        "ball_and_stick": 0.4,
        "space_filling": 1.0,
        "polyhedral": 0.4,
    }
)
DEFAULT_BOND_SIZE_SCALE = 1.0
DEFAULT_AMBIENT_SCALE = 1.0
DEFAULT_BOND_RADIUS = 0.08
DEFAULT_HYDROGEN_BOND_RADIUS = 0.05
DEFAULT_HYDROGEN_BOND_COLOR = Color(0.5, 0.5, 0.5)
DEFAULT_HYDROGEN_BOND_LINE_STYLE = "dashed"
DEFAULT_HYDROGEN_BOND_SEGMENTS = 4
DEFAULT_POLYHEDRON_FILTER = 0.05
DEFAULT_POLYHEDRON_TRANSMIT = 0.3
DEFAULT_ATOM_FINISH = Finish(phong=0.3)
DEFAULT_BOND_FINISH = Finish()
DEFAULT_POLYHEDRON_FINISH = Finish(phong=0.15)

# Cameras, lighting, and scene assembly.
DEFAULT_CAMERA_UP = (0.0, 1.0, 0.0)
DEFAULT_CAMERA_ANGLE = 35.0
DEFAULT_CAMERA_WIDTH = 20.0
DEFAULT_LIGHT_INTENSITY = 1.8
DEFAULT_LIGHT_ANGULAR_DIAMETER = 35.0
DEFAULT_LIGHT_SAMPLES = (9, 9)
DEFAULT_LIGHT_ADAPTIVE = 3
DEFAULT_BACKGROUND_COLOR = Color(1.0, 1.0, 1.0)
DEFAULT_AMBIENT_LIGHT = Color(1.0, 1.0, 1.0)

# Atom labels.
DEFAULT_LABEL_OFFSET = (0.0, 0.0, 0.0)
DEFAULT_LABEL_SIZE = 0.4
DEFAULT_LABEL_THICKNESS = 0.02
DEFAULT_LABEL_FONT = "timrom.ttf"
DEFAULT_LABEL_COLOR = Color(0.0, 0.0, 0.0)

# POV-Ray output and rendering.
DEFAULT_ASPECT_RATIO = 4 / 3
DEFAULT_RENDER_WIDTH = 800
DEFAULT_RENDER_HEIGHT = 600
DEFAULT_RENDER_QUALITY = 5
DEFAULT_RENDER_ANTIALIAS = True
DEFAULT_RENDER_TRANSPARENT = False
DEFAULT_RENDER_DISPLAY = False
DEFAULT_POVRAY_EXECUTABLE = "povray"
DEFAULT_POVRAY_VERSION = "3.7"
