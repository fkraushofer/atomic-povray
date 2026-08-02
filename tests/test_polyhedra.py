import numpy as np
import pytest
from ase import Atoms

from atomic_povray import (
    AtomStyle,
    BondRule,
    Color,
    CoordinationPolyhedronRule,
    CylinderPrimitive,
    DepthShading,
    PolyhedronEdgeStyle,
    PolyhedronStyle,
    PolyhedronStyleOverride,
    StructureModel,
    StyleConfig,
    TriangleMeshPrimitive,
    apply_styles,
    build_geometry,
    get_default_bonds,
    load_structure,
)
from atomic_povray.backends.povray_sdl import _pigment


def _geometry(ligand_positions, **rule_options):
    atoms = Atoms(
        ["Fe", *(["O"] * len(ligand_positions))],
        positions=[(5, 5, 5), *ligand_positions],
        cell=(10, 10, 10),
        pbc=False,
    )
    return build_geometry(
        StructureModel(atoms),
        bond_rules=(BondRule("Fe", "O", 0.5, 2.0),),
        polyhedron_rules=(
            CoordinationPolyhedronRule(
                "Fe", ligand_elements={"O"}, **rule_options
            ),
        ),
    )


def test_tetrahedral_polyhedron_has_outward_faces_and_true_edges():
    geometry = _geometry(
        [
            (6, 6, 6),
            (6, 4, 4),
            (4, 6, 4),
            (4, 4, 6),
        ]
    )

    polyhedron, = geometry.polyhedra
    assert polyhedron.dimension == 3
    assert len(polyhedron.faces) == 4
    assert len(polyhedron.edges) == 6
    vertices = np.asarray(polyhedron.vertices)
    interior = np.mean(vertices, axis=0)
    for face in polyhedron.faces:
        a, b, c = vertices[list(face)]
        assert np.dot(np.cross(b - a, c - a), np.mean((a, b, c), axis=0) - interior) > 0


def test_square_planar_polyhedron_has_no_triangulation_edge():
    geometry = _geometry(
        [(6, 5, 5), (5, 6, 5), (4, 5, 5), (5, 4, 5)]
    )

    polyhedron, = geometry.polyhedra
    assert polyhedron.dimension == 2
    assert len(polyhedron.faces) == 2
    assert len(polyhedron.edges) == 4
    assert all(edge in polyhedron.edges for edge in sorted(polyhedron.edges))


def test_degenerate_polyhedron_can_warn_or_error():
    with pytest.warns(UserWarning, match="degenerate"):
        geometry = _geometry([(6, 5, 5), (4, 5, 5)])
    assert not geometry.polyhedra

    with pytest.raises(ValueError, match="degenerate"):
        _geometry(
            [(6, 5, 5), (4, 5, 5)],
            on_degenerate="error",
        )


def test_expansion_is_an_absolute_radial_distance():
    geometry = _geometry(
        [(6, 5, 5), (5, 6, 5), (4, 5, 5), (5, 4, 5)],
        expansion=0.25,
    )
    distances = np.linalg.norm(
        np.asarray(geometry.polyhedra[0].vertices) - (5, 5, 5), axis=1
    )
    assert distances == pytest.approx([1.25] * 4)


def test_complete_periodic_shell_registers_missing_ligand_instances():
    center = np.array((0.2, 1.0, 1.0))
    offsets = np.array(
        [
            (0.3, 0.3, 0.3),
            (0.3, -0.3, -0.3),
            (-0.3, 0.3, -0.3),
            (-0.3, -0.3, 0.3),
        ]
    )
    ligand_positions = (center + offsets) % 2.0
    structure = StructureModel(
        Atoms(
            ["Fe", "O", "O", "O", "O"],
            positions=[center, *ligand_positions],
            cell=(2, 2, 2),
            pbc=True,
        )
    )
    geometry = build_geometry(
        structure,
        bond_rules=(
            BondRule("Fe", "O", 0.4, 0.7, extension_mode="none"),
        ),
        polyhedron_rules=(
            CoordinationPolyhedronRule("Fe", ligand_elements={"O"}),
        ),
    )

    assert len(geometry.polyhedra) == 1
    assert len(geometry.extension_atoms) == 2
    assert all(atom.position[0] == pytest.approx(-0.1) for atom in geometry.extension_atoms)


def test_polyhedron_style_creates_mesh_and_only_true_edge_cylinders():
    geometry = _geometry(
        [(6, 5, 5), (5, 6, 5), (4, 5, 5), (5, 4, 5)]
    )
    styled = apply_styles(
        geometry,
        StyleConfig(
            draw_atoms=False,
            draw_bonds=False,
            polyhedra={
                "Fe-polyhedron": PolyhedronStyle(
                    color=Color(0.8, 0.2, 0.1, alpha=0.6, filter=0.2),
                    edges=PolyhedronEdgeStyle(
                        visible=True, radius=0.03, color=Color(0.1, 0.1, 0.1)
                    ),
                )
            },
        ),
    )
    meshes = [p for p in styled.primitives if isinstance(p, TriangleMeshPrimitive)]
    edges = [p for p in styled.primitives if isinstance(p, CylinderPrimitive)]
    assert len(meshes) == 1
    assert meshes[0].reference_position == (5.0, 5.0, 5.0)
    assert len(edges) == 4
    assert meshes[0].material.color.transmit == pytest.approx(0.4)
    assert meshes[0].material.color.filter == pytest.approx(0.2)


def test_color_alpha_alias_and_povray_transparency_serialization():
    color = Color(0.8, 0.2, 0.1, alpha=0.6, filter=0.2)
    assert color.transmit == pytest.approx(0.4)
    assert color.alpha == pytest.approx(0.6)
    assert "rgbft <0.8, 0.2, 0.1, 0.2, 0.4>" in _pigment(color)
    assert "color rgb <1, 1, 1>" in _pigment(Color(1, 1, 1))
    assert "rgbf" in _pigment(Color(1, 0, 0, filter=0.5))
    assert "rgbt" in _pigment(Color(1, 0, 0, transmit=0.5))
    with pytest.raises(ValueError, match="only one"):
        Color(1, 0, 0, alpha=0.5, transmit=0.5)


def test_polyhedron_transparency_overrides_inherited_center_color():
    geometry = _geometry(
        [(6, 5, 5), (5, 6, 5), (4, 5, 5), (5, 4, 5)]
    )
    styled = apply_styles(
        geometry,
        StyleConfig(
            draw_atoms=False,
            draw_bonds=False,
            elements={"Fe": AtomStyle(color=Color(0.7, 0.2, 0.1, filter=0.1))},
            default_polyhedron=PolyhedronStyle(filter=0.3, alpha=0.6),
        ),
    )

    mesh = next(p for p in styled.primitives if isinstance(p, TriangleMeshPrimitive))
    assert mesh.material.color == Color(0.7, 0.2, 0.1, filter=0.3, alpha=0.6)


def test_polyhedron_alpha_and_transmit_are_mutually_exclusive():
    with pytest.raises(ValueError, match="only one"):
        PolyhedronStyle(alpha=0.5, transmit=0.5)
    with pytest.raises(ValueError, match="only one"):
        PolyhedronStyleOverride(alpha=0.5, transmit=0.5)


def test_depth_shading_uses_polyhedron_center_reference():
    geometry = _geometry(
        [(6, 5, 5), (5, 6, 5), (4, 5, 5), (5, 4, 5)]
    )
    styled = apply_styles(
        geometry,
        StyleConfig(
            draw_atoms=False,
            draw_bonds=False,
            default_polyhedron=PolyhedronStyle(color=Color(1, 0, 0)),
            depth_shading=DepthShading(
                origin=(0, 0, 0),
                direction=(1, 0, 0),
                decay_length=5,
                target=Color(1, 1, 1),
            ),
        ),
    )
    mesh = next(p for p in styled.primitives if isinstance(p, TriangleMeshPrimitive))
    assert mesh.material.color.green == pytest.approx(1 - np.exp(-1))


def test_relaxed_hematite_builds_expected_coordination_hulls():
    structure = load_structure("tests/data/fe2o3-012-1x1-relaxed.vasp")
    geometry = build_geometry(
        structure,
        bond_rules=get_default_bonds(structure, print_table=False),
        polyhedron_rules=(
            CoordinationPolyhedronRule(
                "Fe", ligand_elements={"O"}, on_degenerate="ignore"
            ),
        ),
    )

    assert len(geometry.polyhedra) == 16
    assert sum(
        len(polyhedron.vertices) == 6 for polyhedron in geometry.polyhedra
    ) == 12
