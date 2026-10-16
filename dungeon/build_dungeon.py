"""Build the Knowledge Dungeon medieval dungeon from dungeon/map.txt.

Coordinate mapping (per spec): grid column c -> X, grid row r -> Z, height -> Y.
Cell centres are at (c + 0.5, y, r + 0.5). The scene is authored Y-up, so the
glTF exporter's Y-up conversion is disabled at export time - see export_glb().

Run headless:      blender --background --python build_dungeon.py
Or exec this file with __name__ == "__main__" from the MCP bridge.
"""

import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import validate_map  # noqa: E402

COLLECTION_NAME = "Dungeon"

WALL_HEIGHT = 3.0
FLOOR_THICKNESS = 0.1
TORCH_HEIGHT = 1.4
CRYSTAL_HEIGHT = 1.4
ALTAR_CELL = (10, 6)

# Blender primitives are Z-aligned; the dungeon is Y-up, so rotate them.
ROT_Z_TO_Y = Matrix.Rotation(math.radians(-90), 4, "X")


# ----------------------------------------------------------------------------
# Primitive helpers
# ----------------------------------------------------------------------------
def _tag(result, material_index):
    """Assign a material slot to the faces created by a bmesh op."""
    faces = set()
    for vert in result["verts"]:
        faces.update(vert.link_faces)
    for face in faces:
        face.material_index = material_index


def add_box(bm, center, size, material_index=0, rotation=None):
    matrix = Matrix.Translation(Vector(center)) @ Matrix.Diagonal(Vector((*size, 1.0)))
    if rotation is not None:
        matrix = matrix @ rotation
    _tag(bmesh.ops.create_cube(bm, size=1.0, matrix=matrix, calc_uvs=True), material_index)


def add_cylinder(
    bm,
    center,
    radius_bottom,
    radius_top,
    depth,
    segments=8,
    material_index=0,
    rotation=None,
    cap_ends=True,
):
    matrix = Matrix.Translation(Vector(center))
    if rotation is not None:
        matrix = matrix @ rotation
    result = bmesh.ops.create_cone(
        bm,
        cap_ends=cap_ends,
        cap_tris=False,
        segments=segments,
        radius1=radius_bottom,
        radius2=radius_top,
        depth=depth,
        matrix=matrix,
        calc_uvs=True,
    )
    _tag(result, material_index)


def add_icosphere(bm, center, scale, material_index=0, subdivisions=1):
    matrix = Matrix.Translation(Vector(center)) @ Matrix.Diagonal(Vector((*scale, 1.0)))
    _tag(
        bmesh.ops.create_icosphere(bm, subdivisions=subdivisions, radius=1.0, matrix=matrix, calc_uvs=True),
        material_index,
    )


def to_object(bm, name, collection, materials):
    mesh = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()

    for mat in materials:
        mesh.materials.append(mat)

    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    return obj


def triangle_count(mesh):
    return sum(len(poly.vertices) - 2 for poly in mesh.polygons)


# ----------------------------------------------------------------------------
# Materials
# ----------------------------------------------------------------------------
def _principled(name, base_color, roughness=0.8, metallic=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    tree = mat.node_tree
    tree.nodes.clear()

    output = tree.nodes.new("ShaderNodeOutputMaterial")
    output.location = (620, 0)
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (300, 0)
    tree.links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    # Socket defaults double as the flat fallback the glTF exporter uses.
    bsdf.inputs["Base Color"].default_value = (*base_color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat, tree, bsdf


def stone_material(name, base_color, noise_scale=7.0, bump_strength=0.25, roughness=0.9):
    """Principled + procedural noise. Nothing is baked into a texture."""
    mat, tree, bsdf = _principled(name, base_color, roughness=roughness)

    coords = tree.nodes.new("ShaderNodeTexCoord")
    coords.location = (-820, 0)

    noise = tree.nodes.new("ShaderNodeTexNoise")
    noise.location = (-620, 0)
    noise.inputs["Scale"].default_value = noise_scale
    noise.inputs["Detail"].default_value = 6.0
    noise.inputs["Roughness"].default_value = 0.6

    ramp = tree.nodes.new("ShaderNodeValToRGB")
    ramp.location = (-400, 60)
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[1].position = 0.65
    ramp.color_ramp.elements[0].color = (base_color[0] * 0.55, base_color[1] * 0.55, base_color[2] * 0.55, 1.0)
    ramp.color_ramp.elements[1].color = (
        min(base_color[0] * 1.35, 1.0),
        min(base_color[1] * 1.35, 1.0),
        min(base_color[2] * 1.35, 1.0),
        1.0,
    )

    bump = tree.nodes.new("ShaderNodeBump")
    bump.location = (-180, -260)
    bump.inputs["Strength"].default_value = bump_strength

    tree.links.new(coords.outputs["Object"], noise.inputs["Vector"])
    tree.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    tree.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    tree.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def plain_material(name, base_color, roughness=0.7, metallic=0.0):
    mat, tree, bsdf = _principled(name, base_color, roughness=roughness, metallic=metallic)
    if metallic:
        bsdf.inputs["Roughness"].default_value = 0.35
    return mat


def emissive_material(name, base_color, color, strength):
    mat, tree, bsdf = _principled(name, base_color, roughness=0.4)
    emission = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
    if emission is not None:
        emission.default_value = (*color, 1.0)
    strength_socket = bsdf.inputs.get("Emission Strength")
    if strength_socket is not None:
        strength_socket.default_value = strength
    return mat


def build_materials():
    mats = {
        "wall": stone_material("StoneWall", (0.42, 0.40, 0.37), noise_scale=6.0),
        "floor": stone_material("StoneFloor", (0.33, 0.31, 0.29), noise_scale=9.0, bump_strength=0.18),
        "ceiling": stone_material("StoneCeiling", (0.26, 0.25, 0.24), noise_scale=5.0, bump_strength=0.12),
        "wood": plain_material("Wood", (0.24, 0.13, 0.06), roughness=0.65),
        "metal": plain_material("Metal", (0.35, 0.36, 0.38), roughness=0.35, metallic=1.0),
        "bone": plain_material("Bone", (0.80, 0.77, 0.66), roughness=0.6),
        "flame": emissive_material("FlameEmissive", (1.0, 0.45, 0.08), (1.0, 0.42, 0.06), 9.0),
        "crystal": emissive_material("CrystalEmissive", (0.25, 0.85, 1.0), (0.20, 0.75, 1.0), 5.0),
    }
    return mats


# ----------------------------------------------------------------------------
# Scene plumbing
# ----------------------------------------------------------------------------
def reset_collection():
    """Remove a previous build of this collection; never touch other objects."""
    existing = bpy.data.collections.get(COLLECTION_NAME)
    if existing is not None:
        for obj in list(existing.objects):
            data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if isinstance(data, bpy.types.Mesh) and data.users == 0:
                bpy.data.meshes.remove(data)
        bpy.data.collections.remove(existing)

    # Drop meshes orphaned by an earlier run of this script only.
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)

    collection = bpy.data.collections.new(COLLECTION_NAME)
    bpy.context.scene.collection.children.link(collection)
    return collection


def make_empty(name, location, collection, parent=None):
    obj = bpy.data.objects.new(name, None)
    obj.empty_display_type = "PLAIN_AXES"
    obj.empty_display_size = 0.3
    obj.location = location
    collection.objects.link(obj)
    if parent is not None:
        obj.parent = parent
        obj.matrix_parent_inverse = parent.matrix_world.inverted()
    return obj


def parent_to(child, parent):
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()


def cell_center(col, row, height=0.0):
    return (col + 0.5, height, row + 0.5)


# ----------------------------------------------------------------------------
# Structure
# ----------------------------------------------------------------------------
def build_walls(grid, collection, mats):
    bm = bmesh.new()
    count = 0
    for row_index, row in enumerate(grid):
        for col_index, char in enumerate(row):
            if char == "#":
                add_box(bm, cell_center(col_index, row_index, WALL_HEIGHT / 2), (1.0, WALL_HEIGHT, 1.0))
                count += 1
    obj = to_object(bm, "Walls", collection, [mats["wall"]])
    return obj, count


def build_floor(grid, collection, mats):
    bm = bmesh.new()
    count = 0
    for row_index, row in enumerate(grid):
        for col_index, char in enumerate(row):
            if char != "#":
                # Top surface sits exactly at y = 0.
                add_box(
                    bm,
                    cell_center(col_index, row_index, -FLOOR_THICKNESS / 2),
                    (1.0, FLOOR_THICKNESS, 1.0),
                )
                count += 1
    return to_object(bm, "Floor", collection, [mats["floor"]]), count


def build_ceiling(grid, collection, mats):
    width = max(len(row) for row in grid)
    height = len(grid)
    bm = bmesh.new()
    verts = [
        bm.verts.new((0.0, WALL_HEIGHT, 0.0)),
        bm.verts.new((width, WALL_HEIGHT, 0.0)),
        bm.verts.new((width, WALL_HEIGHT, height)),
        bm.verts.new((0.0, WALL_HEIGHT, height)),
    ]
    face = bm.faces.new(verts)
    bm.normal_update()
    if face.normal.y > 0:  # ceiling must face down into the room
        face.normal_flip()
    return to_object(bm, "Ceiling", collection, [mats["ceiling"]]), 1


# ----------------------------------------------------------------------------
# Props
# ----------------------------------------------------------------------------
def build_altar(collection, mats):
    col, row = ALTAR_CELL
    center = cell_center(col, row, 0.0)

    empty = make_empty("Altar", center, collection)

    bm = bmesh.new()
    add_box(bm, cell_center(col, row, 0.5), (0.8, 1.0, 0.8))
    block = to_object(bm, "AltarBlock", collection, [mats["wall"]])
    parent_to(block, empty)

    bm = bmesh.new()
    add_icosphere(bm, cell_center(col, row, CRYSTAL_HEIGHT), (0.22, 0.30, 0.22), subdivisions=1)
    crystal = to_object(bm, "AltarCrystal", collection, [mats["crystal"]])
    parent_to(crystal, empty)
    return empty


def build_lectern(collection, mats, col=1, row=1):
    center = cell_center(col, row, 0.0)
    empty = make_empty("Hint_Lectern", center, collection)

    bm = bmesh.new()
    add_cylinder(bm, cell_center(col, row, 0.04), 0.28, 0.24, 0.08, segments=8, rotation=ROT_Z_TO_Y)
    add_cylinder(bm, cell_center(col, row, 0.58), 0.07, 0.07, 1.0, segments=8, rotation=ROT_Z_TO_Y)
    # Slanted reading surface.
    add_box(bm, cell_center(col, row, 1.12), (0.46, 0.05, 0.36), rotation=Matrix.Rotation(math.radians(22), 4, "X"))
    lectern = to_object(bm, "Lectern", collection, [mats["wood"]])
    parent_to(lectern, empty)
    return empty, lectern


def build_braziers(grid, collection, mats):
    """Life_1/2/3 empties at the B cells, each with a brazier and a flame."""
    brazier_cells = validate_map.find(grid, "B")
    empties = []
    for index, (col, row) in enumerate(brazier_cells, start=1):
        empty = make_empty(f"Life_{index}", cell_center(col, row, 0.0), collection)

        bm = bmesh.new()
        # Bowl, stem, three feet.
        add_cylinder(bm, cell_center(col, row, 0.60), 0.16, 0.30, 0.24, segments=8, rotation=ROT_Z_TO_Y)
        add_cylinder(bm, cell_center(col, row, 0.27), 0.06, 0.06, 0.42, segments=6, rotation=ROT_Z_TO_Y)
        for angle in (0, 120, 240):
            rad = math.radians(angle)
            foot = (
                col + 0.5 + math.cos(rad) * 0.20,
                0.05,
                row + 0.5 + math.sin(rad) * 0.20,
            )
            add_box(bm, foot, (0.07, 0.10, 0.07))
        brazier = to_object(bm, f"Brazier_{index}", collection, [mats["metal"]])
        parent_to(brazier, empty)

        bm = bmesh.new()
        add_cylinder(bm, cell_center(col, row, 0.74), 0.06, 0.05, 0.10, segments=6, rotation=ROT_Z_TO_Y)
        add_cylinder(bm, cell_center(col, row, 0.90), 0.11, 0.0, 0.26, segments=6, rotation=ROT_Z_TO_Y)
        flame = to_object(bm, f"Flame_{index}", collection, [mats["flame"]])
        parent_to(flame, empty)

        empties.append(empty)
    return empties


def build_torches(grid, collection):
    """Torch markers are empties only, per spec."""
    return [
        make_empty(f"Torch_{col}_{row}", cell_center(col, row, TORCH_HEIGHT), collection)
        for col, row in validate_map.find(grid, "T")
    ]


# ----------------------------------------------------------------------------
# Enemies
# ----------------------------------------------------------------------------
def build_guardian(collection, mats, col, row):
    """One low-poly skeletal guardian, bone + metal, facing the altar."""
    altar_x, altar_z = ALTAR_CELL[0] + 0.5, ALTAR_CELL[1] + 0.5
    dx, dz = altar_x - (col + 0.5), altar_z - (row + 0.5)
    facing = math.atan2(-dz, dx)

    bone, metal = 0, 1
    bm = bmesh.new()

    def at(dx_off, y, dz_off):
        return (col + 0.5 + dx_off, y, row + 0.5 + dz_off)

    # Skull, jaw, neck
    add_icosphere(bm, at(0.0, 1.44, 0.0), (0.15, 0.17, 0.15), bone)
    add_box(bm, at(0.06, 1.30, 0.0), (0.16, 0.07, 0.13), bone)
    add_cylinder(bm, at(0.0, 1.22, 0.0), 0.05, 0.05, 0.09, segments=6, material_index=bone, rotation=ROT_Z_TO_Y)

    # Spine
    for i in range(5):
        add_box(bm, at(0.0, 1.12 - i * 0.09, 0.0), (0.06, 0.07, 0.06), bone)

    # Ribcage: two open tubes read as ribs
    for y in (1.05, 0.94):
        add_cylinder(bm, at(0.0, y, 0.0), 0.19, 0.19, 0.06, segments=10, material_index=bone, rotation=ROT_Z_TO_Y, cap_ends=False)

    # Pelvis
    add_box(bm, at(0.0, 0.86, 0.0), (0.20, 0.09, 0.13), bone)

    # Arms
    for side in (-1, 1):
        add_icosphere(bm, at(0.0, 1.09, side * 0.22), (0.11, 0.09, 0.11), metal)
        add_cylinder(bm, at(0.0, 0.94, side * 0.26), 0.045, 0.045, 0.28, segments=6, material_index=bone, rotation=ROT_Z_TO_Y)
        add_cylinder(bm, at(0.03, 0.72, side * 0.26), 0.04, 0.04, 0.26, segments=6, material_index=bone, rotation=ROT_Z_TO_Y)
        add_box(bm, at(0.04, 0.57, side * 0.26), (0.08, 0.08, 0.07), bone)

    # Legs
    for side in (-1, 1):
        add_cylinder(bm, at(0.0, 0.64, side * 0.09), 0.055, 0.05, 0.38, segments=6, material_index=bone, rotation=ROT_Z_TO_Y)
        add_cylinder(bm, at(0.0, 0.28, side * 0.09), 0.05, 0.045, 0.34, segments=6, material_index=bone, rotation=ROT_Z_TO_Y)
        add_box(bm, at(0.04, 0.05, side * 0.09), (0.17, 0.06, 0.09), bone)

    # Metal: shield on the left, sword on the right
    shield = Matrix.Rotation(math.radians(90), 4, "Y")
    add_cylinder(bm, at(-0.10, 0.72, -0.34), 0.20, 0.20, 0.05, segments=10, material_index=metal, rotation=shield)
    add_cylinder(bm, at(0.12, 0.86, 0.30), 0.03, 0.03, 0.20, segments=6, material_index=metal, rotation=ROT_Z_TO_Y)
    add_box(bm, at(0.12, 0.64, 0.30), (0.07, 0.26, 0.02), metal)
    add_cylinder(bm, at(0.12, 0.50, 0.30), 0.045, 0.0, 0.12, segments=4, material_index=metal, rotation=ROT_Z_TO_Y)

    name = f"Enemy_{col}_{row}"
    obj = to_object(bm, name, collection, [mats["bone"], mats["metal"]])
    obj.location = cell_center(col, row, 0.0)
    obj.rotation_euler = (0.0, facing, 0.0)
    return obj


# ----------------------------------------------------------------------------
# Dressings
# ----------------------------------------------------------------------------
def build_props(collection, mats):
    """Barrel and crate, each pushed against a wall so the route stays clear."""
    barrel = make_empty("Barrel", (13.5, 0.0, 1.25), collection)
    bm = bmesh.new()
    add_cylinder(bm, (13.5, 0.36, 1.25), 0.26, 0.29, 0.72, segments=12, rotation=ROT_Z_TO_Y)
    for y in (0.16, 0.56):
        add_cylinder(bm, (13.5, y, 1.25), 0.295, 0.295, 0.05, segments=12, rotation=ROT_Z_TO_Y, cap_ends=False)
    body = to_object(bm, "BarrelMesh", collection, [mats["wood"]])
    parent_to(body, barrel)

    crate = make_empty("Crate", (13.7, 0.0, 6.5), collection)
    bm = bmesh.new()
    add_box(bm, (13.7, 0.25, 6.5), (0.46, 0.50, 0.46))
    for dy in (-0.16, 0.16):
        add_box(bm, (13.7, 0.25 + dy, 6.5), (0.50, 0.08, 0.50))
    body = to_object(bm, "CrateMesh", collection, [mats["wood"]])
    parent_to(body, crate)
    return [barrel, crate]


# ----------------------------------------------------------------------------
# Build + export
# ----------------------------------------------------------------------------
EXPECTED_MATERIALS = {
    "StoneWall",
    "StoneFloor",
    "StoneCeiling",
    "Wood",
    "Metal",
    "Bone",
    "FlameEmissive",
    "CrystalEmissive",
}


def build():
    grid = validate_map.load_grid()
    errors, info = validate_map.validate(grid)
    if errors:
        raise SystemExit("map.txt failed validation:\n  - " + "\n  - ".join(errors))

    collection = reset_collection()
    mats = build_materials()

    walls, wall_count = build_walls(grid, collection, mats)
    floor, floor_count = build_floor(grid, collection, mats)
    ceiling, _ = build_ceiling(grid, collection, mats)

    altar = build_altar(collection, mats)
    lectern, _ = build_lectern(collection, mats, *validate_map.find(grid, "H")[0])
    lives = build_braziers(grid, collection, mats)
    torches = build_torches(grid, collection)

    enemies = [build_guardian(collection, mats, col, row) for col, row in validate_map.find(grid, "E")]
    build_props(collection, mats)

    report = {
        "wall_cells": wall_count,
        "floor_cells": floor_count,
        "wall_blocks_in_mesh": len(walls.data.polygons) // 6,
        "objects": len(collection.objects),
        "materials": sorted(m.name for m in bpy.data.materials if m.name in EXPECTED_MATERIALS),
        "total_triangles": sum(
            triangle_count(o.data) for o in collection.objects if o.type == "MESH"
        ),
        "altar_path": info["altar_path"],
    }
    return collection, report


def export_glb(collection, path, blend_path=None):
    """Export only the Dungeon collection, as Y-up glTF binary.

    The scene is already authored Y-up (height on +Y, per spec), so the
    exporter's Blender-Z-up -> glTF-Y-up conversion is disabled to avoid
    rotating the dungeon a second time. The file's up axis stays Y.
    """
    bpy.ops.object.select_all(action="DESELECT")
    for obj in collection.objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = next(o for o in collection.objects)

    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_yup=False,  # authored Y-up already; keep it that way
        export_cameras=False,
        export_lights=False,
        export_materials="EXPORT",
        export_extras=True,
    )
    if blend_path:
        bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    return path


if __name__ == "__main__":
    collection, report = build()
    print("BUILD REPORT:", report)
    export_glb(
        collection,
        os.path.join(HERE, "dungeon.glb"),
        blend_path=os.path.join(HERE, "dungeon.blend"),
    )
    print("EXPORTED:", os.path.join(HERE, "dungeon.glb"))