"""Rebuild the Knowledge Dungeon level: wider corridors, baked AO/GI, better
walls, and a water puddle asset.

Key change: CELL = 2.0 metres per grid cell (was 1.0). The maze topology in
map.txt is unchanged, so corridors go from 1 m to 2 m wide and the whole
dungeon becomes 82 x 62 m. The frontend mirrors this with CELL_SIZE = 2.

Lighting realism without a realtime GI solver: per-vertex ambient occlusion is
ray-marched against the wall grid, and warm bounce from the torches + the
altar crystal is added on top. Both are written into a COLOR attribute, which
the glTF exporter turns into COLOR_0 - three.js multiplies that straight into
the material, so creases darken and torch pools glow with no runtime cost.

Run headless:
    blender --background dungeon.blend --python build_level.py
"""

import json
import math
import os
import struct
import sys

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

TEX = os.path.join(HERE, "textures")
os.makedirs(TEX, exist_ok=True)

# ------------------------------------------------------------------ config --
CELL = 2.0                 # metres per grid cell (was 1.0)
WALL_HEIGHT = 3.0
PLINTH_TOP = 0.45
CORNICE_BOT = 2.55
INSET = 0.14                # depth of the recessed field
FLOOR_THICKNESS = 0.1
TILE = 4.0                 # metres per baked texture tile
FLOOR_SUBDIV = 3            # quads per cell edge (AO resolution)
CEILING_SUBDIV = 1.5        # metres per ceiling quad
TORCH_HEIGHT = 1.55
CRYSTAL_HEIGHT = 1.45

AO_DIRS = 10                # rays per hemisphere
AO_STEPS = 26
AO_MAX_DIST = 7.0
BOUNCE_GAIN = 0.55

ROT_Z_TO_Y = Matrix.Rotation(math.radians(-90), 4, "X")

grid = [l for l in open(os.path.join(HERE, "map.txt")).read().splitlines() if l.strip()]
H = len(grid)
W = max(len(l) for l in grid)

# occupancy grid: True = solid wall (for the AO ray march)
OCC = np.zeros((H, W), dtype=bool)
for r, line in enumerate(grid):
    for c, ch in enumerate(line):
        OCC[r, c] = ch == "#"


def cell_rect(c, r):
    return c * CELL, (c + 1) * CELL, r * CELL, (r + 1) * CELL


def cell_center(c, r, h=0.0):
    return (c + 0.5) * CELL, h, (r + 0.5) * CELL


def is_floor(c, r):
    if 0 <= r < H and 0 <= c < W:
        return grid[r][c] != "#"
    return False


def cell_at(x, z):
    return int(math.floor(x / CELL)), int(math.floor(z / CELL))


def torch_cells():
    out = []
    for r, line in enumerate(grid):
        for c, ch in enumerate(line):
            if ch == "T":
                out.append((c, r))
    return out


def find(ch):
    out = []
    for r, line in enumerate(grid):
        for c, k in enumerate(line):
            if k == ch:
                out.append((c, r))
    return out


def validate():
    """Local checks: rectangular grid, required markers, altar reachable."""
    errors = []
    if len({len(l) for l in grid}) != 1:
        errors.append(f"ragged rows: widths {sorted({len(l) for l in grid})}")
    for ch, label in (("S", "spawn"), ("Q", "altar"), ("H", "lectern")):
        if not find(ch):
            errors.append(f"missing {label} marker '{ch}'")
    if len(find("B")) != 3:
        errors.append(f"expected 3 braziers, got {len(find('B'))}")
    if not find("T"):
        errors.append("no torches")

    if not errors:
        spawn = find("S")[0]
        altar = find("Q")[0]
        seen = {spawn}
        queue = [spawn]
        while queue:
            c, r = queue.pop()
            for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                n = (c + dc, r + dr)
                if n in seen or not (0 <= n[1] < H and 0 <= n[0] < W):
                    continue
                if grid[n[1]][n[0]] == "#":
                    continue
                seen.add(n)
                queue.append(n)
        if altar not in seen:
            errors.append("altar is not reachable from spawn")
    if errors:
        raise SystemExit("map.txt failed validation:\n  - " + "\n  - ".join(errors))
    return True


# ---------------------------------------------------------------- AO / GI ---
def bake_vertex_light(obj, torches, altar, strength=1.0):
    """Write a COLOR attribute: ray-marched AO * torch/altar bounce.

    Rays are cast in the hemisphere around each vertex normal (so floors, walls
    and ceilings are all lit from the right side) and occlusion is weighted by
    how far away the hit was - a crease darkens, an open floor does not.
    """
    me = obj.data
    nv = len(me.vertices)
    co = np.empty(nv * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(nv, 3)

    normals = np.empty(nv * 3, dtype=np.float64)
    me.vertex_normals.foreach_get("vector", normals)
    normals = normals.reshape(nv, 3)
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-9)

    # tangent frame per vertex (normals here are axis-aligned in practice)
    helper = np.tile(np.array([0.0, 1.0, 0.0]), (nv, 1))
    flip = np.abs(normals[:, 1]) > 0.9
    helper[flip] = np.array([1.0, 0.0, 0.0])
    tangent = np.cross(helper, normals)
    tangent /= np.maximum(np.linalg.norm(tangent, axis=1, keepdims=True), 1e-9)
    bitan = np.cross(normals, tangent)

    # cosine-weighted hemisphere samples, same set for every vertex
    samples = []
    for i in range(AO_DIRS):
        a = (i + 0.5) / AO_DIRS * math.tau
        r = math.sqrt((i + 0.5) / AO_DIRS)
        samples.append((math.cos(a) * r, math.sin(a) * r, math.sqrt(max(0.0, 1.0 - r * r))))
    samples = np.array(samples)

    step = AO_MAX_DIST / AO_STEPS
    origin = co + normals * 0.03
    occlusion = np.zeros(nv)

    for sx, sy, sz in samples:
        direction = (tangent * sx + bitan * sy + normals * sz)
        direction /= np.maximum(np.linalg.norm(direction, axis=1, keepdims=True), 1e-9)
        hit = np.full(nv, np.inf)
        for s in range(1, AO_STEPS + 1):
            dist = step * s
            q = origin + direction * dist
            cc = np.floor(q[:, 0] / CELL).astype(np.int64)
            rr = np.floor(q[:, 2] / CELL).astype(np.int64)
            inside = (cc >= 0) & (cc < W) & (rr >= 0) & (rr < H)
            solid = np.zeros(nv, dtype=bool)
            solid[inside] = OCC[rr[inside], cc[inside]]
            # Only walls occlude. The floor/ceiling planes are left out on
            # purpose: we want contact darkening in the corners, not a closed
            # box that crushes every corridor to black.
            hit = np.where((solid) & np.isinf(hit), dist, hit)

        blocked = np.isfinite(hit)
        weight = np.where(blocked, np.clip(1.0 - hit / AO_MAX_DIST, 0.0, 1.0) ** 1.4, 0.0)
        occlusion += weight / AO_DIRS

    ao = np.clip(1.0 - occlusion, 0.0, 1.0)
    ao = 0.46 + 0.54 * ao ** 1.1           # contact darkening, never black

    # warm bounce from the torches + violet from the altar crystal
    glow = np.zeros((nv, 3))
    for (c, r) in torches:
        tp = np.array(cell_center(c, r, TORCH_HEIGHT))
        d2 = ((co - tp) ** 2).sum(axis=1) + 1.2
        w = BOUNCE_GAIN / (1.0 + d2 * 0.55)
        glow[:, 0] += w * 1.0
        glow[:, 1] += w * 0.52
        glow[:, 2] += w * 0.22
    ap = np.array(cell_center(altar[0], altar[1], CRYSTAL_HEIGHT))
    d2 = ((co - ap) ** 2).sum(axis=1) + 1.6
    w = BOUNCE_GAIN * 0.9 / (1.0 + d2 * 0.35)
    glow[:, 0] += w * 0.62
    glow[:, 1] += w * 0.40
    glow[:, 2] += w * 1.0

    colour = np.empty((nv, 4), dtype=np.float32)
    colour[:, :3] = (ao[:, None] * (1.0 + glow * strength)).clip(0.0, 1.6)
    colour[:, 3] = 1.0

    attr = me.color_attributes.get("Col")
    if attr is None:
        attr = me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="POINT")
    attr.data.foreach_set("color", colour.ravel())
    return {"ao_mean": round(float(ao.mean()), 3), "ao_min": round(float(ao.min()), 3),
            "ao_max": round(float(ao.max()), 3)}


def cell_at_arr(q):
    cc = np.floor(q[:, 0] / CELL).astype(np.int64)
    rr = np.floor(q[:, 2] / CELL).astype(np.int64)
    return cc, rr


# ----------------------------------------------------------------- helpers --
def link(obj):
    coll = bpy.data.collections.get("Dungeon")
    coll.objects.link(obj)
    return obj


def new_object(name, bm, materials):
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    for m in materials:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    return link(ob)


def add_box(bm, center, size, material_index=0, rotation=None):
    matrix = Matrix.Translation(Vector(center)) @ Matrix.Diagonal(Vector((*size, 1.0)))
    if rotation is not None:
        matrix = matrix @ rotation
    res = bmesh.ops.create_cube(bm, size=1.0, matrix=matrix, calc_uvs=True)
    faces = set()
    for v in res["verts"]:
        faces.update(v.link_faces)
    for f in faces:
        f.material_index = material_index


def add_cylinder(bm, center, r_bottom, r_top, depth, segments=8, material_index=0,
                 rotation=None, cap_ends=True):
    matrix = Matrix.Translation(Vector(center))
    if rotation is not None:
        matrix = matrix @ rotation
    res = bmesh.ops.create_cone(bm, cap_ends=cap_ends, cap_tris=False, segments=segments,
                                radius1=r_bottom, radius2=r_top, depth=depth,
                                matrix=matrix, calc_uvs=True)
    faces = set()
    for v in res["verts"]:
        faces.update(v.link_faces)
    for f in faces:
        f.material_index = material_index


def add_icosphere(bm, center, scale, material_index=0, subdivisions=1):
    matrix = Matrix.Translation(Vector(center)) @ Matrix.Diagonal(Vector((*scale, 1.0)))
    res = bmesh.ops.create_icosphere(bm, subdivisions=subdivisions, radius=1.0,
                                     matrix=matrix, calc_uvs=True)
    faces = set()
    for v in res["verts"]:
        faces.update(v.link_faces)
    for f in faces:
        f.material_index = material_index


def make_empty(name, location, parent=None):
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_type = "PLAIN_AXES"
    ob.empty_display_size = 0.3
    ob.location = location
    link(ob)
    if parent is not None:
        ob.parent = parent
        ob.matrix_parent_inverse = parent.matrix_world.inverted()
    return ob


def parent_to(child, parent):
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()


# -------------------------------------------------------------- materials ---
def principled(name, base, rough=0.85, metallic=0.0):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    return mat


def emissive(name, base, color, strength):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    bsdf.inputs["Base Color"].default_value = (*base, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.4
    e = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
    e.default_value = (*color, 1.0)
    if "Emission Strength" in bsdf.inputs:
        bsdf.inputs["Emission Strength"].default_value = strength
    return mat


def build_materials():
    return {
        "stone_wall": principled("stone_wall", (0.5, 0.5, 0.5), rough=0.75),
        "stone_floor": principled("stone_floor", (0.42, 0.41, 0.40), rough=0.9),
        "ceiling_stone": principled("ceiling_stone", (0.40, 0.40, 0.40), rough=0.95),
        "wood": principled("wood", (0.16, 0.10, 0.05), rough=0.78),
        "metal": principled("metal", (0.10, 0.10, 0.11), rough=0.45, metallic=1.0),
        "bone": principled("bone", (0.62, 0.58, 0.46), rough=0.6),
        "emissive_flame": emissive("emissive_flame", (1.0, 0.45, 0.1), (1.0, 0.38, 0.06), 9.0),
        "emissive_crystal": emissive("emissive_crystal", (0.3, 0.9, 1.0), (0.25, 0.8, 1.0), 6.0),
        # water: very smooth dielectric so the environment map gives it mirror sheen
        "water_puddle": principled("water_puddle", (0.012, 0.022, 0.030), rough=0.035),
    }


# ------------------------------------------------------------- geometry -----
def build_walls(mats):
    bm = bmesh.new()

    def quad_x(sign, px, y0, y1, z0, z1):
        vs = [bm.verts.new((px, y0, z0)), bm.verts.new((px, y1, z0)),
              bm.verts.new((px, y1, z1)), bm.verts.new((px, y0, z1))]
        if sign < 0:
            vs.reverse()
        bm.faces.new(vs)

    def quad_y(sign, py, x0, x1, z0, z1):
        vs = [bm.verts.new((x0, py, z1)), bm.verts.new((x1, py, z1)),
              bm.verts.new((x1, py, z0)), bm.verts.new((x0, py, z0))]
        if sign < 0:
            vs.reverse()
        bm.faces.new(vs)

    def quad_z(sign, pz, y0, y1, x0, x1):
        vs = [bm.verts.new((x0, y0, pz)), bm.verts.new((x1, y0, pz)),
              bm.verts.new((x1, y1, pz)), bm.verts.new((x0, y1, pz))]
        if sign < 0:
            vs.reverse()
        bm.faces.new(vs)

    wall_cells = [(c, r) for r in range(H) for c in range(W) if not is_floor(c, r)]
    for (c, r) in wall_cells:
        x0, x1, z0, z1 = cell_rect(c, r)
        for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            if not is_floor(c + dc, r + dr):
                continue
            if dc == 1:
                quad_x(1, x1, 0.0, PLINTH_TOP, z0, z1)
                quad_x(1, x1 - INSET, PLINTH_TOP, CORNICE_BOT, z0, z1)
                quad_x(1, x1, CORNICE_BOT, WALL_HEIGHT, z0, z1)
            elif dc == -1:
                quad_x(-1, x0, 0.0, PLINTH_TOP, z0, z1)
                quad_x(-1, x0 + INSET, PLINTH_TOP, CORNICE_BOT, z0, z1)
                quad_x(-1, x0, CORNICE_BOT, WALL_HEIGHT, z0, z1)
            elif dr == 1:
                quad_z(1, z1, 0.0, PLINTH_TOP, x0, x1)
                quad_z(1, z1 - INSET, PLINTH_TOP, CORNICE_BOT, x0, x1)
                quad_z(1, z1, CORNICE_BOT, WALL_HEIGHT, x0, x1)
            else:
                quad_z(-1, z0, 0.0, PLINTH_TOP, x0, x1)
                quad_z(-1, z0 + INSET, PLINTH_TOP, CORNICE_BOT, x0, x1)
                quad_z(-1, z0, CORNICE_BOT, WALL_HEIGHT, x0, x1)
        quad_y(1, PLINTH_TOP, x0, x1, z0, z1)
        quad_y(-1, CORNICE_BOT, x0, x1, z0, z1)

    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)

    # Subdivide the wall faces so the baked vertex AO can resolve corners.
    bmesh.ops.subdivide_edges(
        bm,
        edges=[e for e in bm.edges if len(e.link_faces) == 2],
        cuts=2,
        use_grid_fill=True,
    )
    bm.normal_update()

    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        for loop in f.loops:
            co = loop.vert.co
            if ax == 0:
                u, v = co.z, co.y
            elif ax == 1:
                u, v = co.x, co.z
            else:
                u, v = co.x, co.y
            loop[uv].uv = (u / TILE, v / TILE)

    ob = new_object("Walls", bm, [mats["stone_wall"]])
    return ob, wall_cells


def build_floor(mats):
    bm = bmesh.new()
    step = CELL / FLOOR_SUBDIV
    for r in range(H):
        for c in range(W):
            if not is_floor(c, r):
                continue
            x0, _, z0, _ = cell_rect(c, r)
            for i in range(FLOOR_SUBDIV):
                for j in range(FLOOR_SUBDIV):
                    ax, az = x0 + i * step, z0 + j * step
                    # Wound so the normal points +Y: the floor is seen from above,
                    # and the wrong order would be back-face culled and invisible.
                    vs = [bm.verts.new((ax, 0.0, az)), bm.verts.new((ax, 0.0, az + step)),
                          bm.verts.new((ax + step, 0.0, az + step)), bm.verts.new((ax + step, 0.0, az))]
                    bm.faces.new(vs)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    # skirt so the floor never shows a gap at the walls
    for r in range(H):
        for c in range(W):
            if not is_floor(c, r):
                continue
            x0, x1, z0, z1 = cell_rect(c, r)
            if not is_floor(c + 1, r):
                add_box(bm, ((x1, -FLOOR_THICKNESS / 2, (z0 + z1) / 2)), (FLOOR_THICKNESS, FLOOR_THICKNESS, CELL))
            if not is_floor(c - 1, r):
                add_box(bm, ((x0, -FLOOR_THICKNESS / 2, (z0 + z1) / 2)), (FLOOR_THICKNESS, FLOOR_THICKNESS, CELL))
            if not is_floor(c, r + 1):
                add_box(bm, (((x0 + x1) / 2, -FLOOR_THICKNESS / 2, z1)), (CELL, FLOOR_THICKNESS, FLOOR_THICKNESS))
            if not is_floor(c, r - 1):
                add_box(bm, (((x0 + x1) / 2, -FLOOR_THICKNESS / 2, z0)), (CELL, FLOOR_THICKNESS, FLOOR_THICKNESS))

    # world-planar UVs so the floor texture tiles at a constant metre scale
    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        ax = max(range(3), key=lambda i: abs(f.normal[i]))
        for loop in f.loops:
            co = loop.vert.co
            u, v = (co.x / TILE, co.z / TILE) if ax != 1 else (co.x / TILE, co.y / TILE)
            loop[uv].uv = (u, v)
    return new_object("Floor", bm, [mats["stone_floor"]])


def build_ceiling(mats):
    bm = bmesh.new()
    w, h = W * CELL, H * CELL
    nx = int(math.ceil(w / CEILING_SUBDIV))
    nz = int(math.ceil(h / CEILING_SUBDIV))
    for i in range(nx):
        for j in range(nz):
            ax, az = i * CEILING_SUBDIV, j * CEILING_SUBDIV
            bx = min(ax + CEILING_SUBDIV, w)
            bz = min(az + CEILING_SUBDIV, h)
            vs = [bm.verts.new((ax, WALL_HEIGHT, az)), bm.verts.new((bx, WALL_HEIGHT, az)),
                  bm.verts.new((bx, WALL_HEIGHT, bz)), bm.verts.new((ax, WALL_HEIGHT, bz))]
            bm.faces.new(vs)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for loop in f.loops:
            co = loop.vert.co
            loop[uv].uv = (co.x / TILE, co.z / TILE)
    ob = new_object("Ceiling", bm, [mats["ceiling_stone"]])
    ob.data.polygons.foreach_set("use_smooth", [False] * len(ob.data.polygons))
    return ob


def build_props(mats):
    altar_cell = find("Q")[0]
    lectern_cell = find("H")[0]
    brazier_cells = find("B")
    spawn_cell = find("S")[0]

    make_empty("Spawn", cell_center(spawn_cell[0], spawn_cell[1]))
    altar = make_empty("Altar", cell_center(altar_cell[0], altar_cell[1]))
    bm = bmesh.new()
    add_box(bm, cell_center(altar_cell[0], altar_cell[1], 0.6), (1.5, 1.2, 1.5))
    add_box(bm, cell_center(altar_cell[0], altar_cell[1], 1.28), (1.75, 0.16, 1.75))
    block = new_object("Altar_Block", bm, [mats["stone_wall"]])
    parent_to(block, altar)
    bm = bmesh.new()
    add_icosphere(bm, cell_center(altar_cell[0], altar_cell[1], CRYSTAL_HEIGHT), (0.3, 0.42, 0.3), subdivisions=1)
    crystal = new_object("AltarCrystal", bm, [mats["emissive_crystal"]])
    parent_to(crystal, altar)

    lectern = make_empty("Hint_Lectern", cell_center(lectern_cell[0], lectern_cell[1]))
    bm = bmesh.new()
    lc, lr = lectern_cell
    add_cylinder(bm, cell_center(lc, lr, 0.06), 0.42, 0.36, 0.12, segments=10, rotation=ROT_Z_TO_Y)
    add_cylinder(bm, cell_center(lc, lr, 0.72), 0.10, 0.10, 1.25, segments=8, rotation=ROT_Z_TO_Y)
    add_box(bm, cell_center(lc, lr, 1.42), (0.78, 0.08, 0.6), rotation=Matrix.Rotation(math.radians(22), 4, "X"))
    body = new_object("Lectern", bm, [mats["wood"]])
    body.name = "Hint_Lectern_Mesh"
    parent_to(body, lectern)
    bm = bmesh.new()
    add_box(bm, cell_center(lc, lr, 1.49), (0.62, 0.04, 0.46), rotation=Matrix.Rotation(math.radians(22), 4, "X"))
    top = new_object("Hint_Lectern_Top", bm, [mats["bone"]])
    parent_to(top, lectern)

    for index, (c, r) in enumerate(brazier_cells, start=1):
        life = make_empty(f"Life_{index}", cell_center(c, r))
        bm = bmesh.new()
        add_cylinder(bm, cell_center(c, r, 0.85), 0.24, 0.44, 0.36, segments=10, rotation=ROT_Z_TO_Y)
        add_cylinder(bm, cell_center(c, r, 0.38), 0.09, 0.09, 0.62, segments=6, rotation=ROT_Z_TO_Y)
        for a in (0, 120, 240):
            rad = math.radians(a)
            add_box(bm, (c * CELL + CELL * 0.5 + math.cos(rad) * 0.3, 0.08,
                         r * CELL + CELL * 0.5 + math.sin(rad) * 0.3), (0.1, 0.16, 0.1))
        brazier = new_object(f"Brazier_{index}", bm, [mats["metal"]])
        parent_to(brazier, life)
        bm = bmesh.new()
        add_cylinder(bm, cell_center(c, r, 1.10), 0.09, 0.07, 0.16, segments=6, rotation=ROT_Z_TO_Y)
        add_cylinder(bm, cell_center(c, r, 1.34), 0.17, 0.0, 0.40, segments=6, rotation=ROT_Z_TO_Y)
        flame = new_object(f"Flame_{index}", bm, [mats["emissive_flame"]])
        parent_to(flame, life)

    for c, r in torch_cells():
        # Markers are cell anchors at y = 0 (like every other marker); the
        # burning height is a lighting decision and lives in the frontend.
        make_empty(f"Torch_{c}_{r}", cell_center(c, r, 0.0))

    # a couple of crates + barrels against walls
    for name, loc, kind in (("Prop_Barrel", (7.0, 0.0, 55.6), "barrel"),
                            ("Prop_Barrel_4", (15.0, 0.0, 5.6), "barrel"),
                            ("Prop_Crate", (27.4, 0.0, 13.0), "crate"),
                            ("Prop_Crate_2", (27.4, 0.0, 49.0), "crate"),
                            ("Prop_Crate_5", (54.0, 0.0, 9.5), "crate")):
        empty = make_empty(name, loc)
        bm = bmesh.new()
        if kind == "barrel":
            add_cylinder(bm, (loc[0], 0.55, loc[2]), 0.40, 0.45, 1.1, segments=12, rotation=ROT_Z_TO_Y)
            for y in (0.28, 0.82):
                add_cylinder(bm, (loc[0], y, loc[2]), 0.46, 0.46, 0.07, segments=12,
                             rotation=ROT_Z_TO_Y, cap_ends=False)
        else:
            add_box(bm, (loc[0], 0.38, loc[2]), (0.75, 0.76, 0.75))
            for dy in (-0.24, 0.24):
                add_box(bm, (loc[0], 0.38 + dy, loc[2]), (0.81, 0.1, 0.81))
        mesh = new_object(f"{name}_Mesh", bm, [mats["wood"]])
        mesh.name = name.replace("Prop_", "Prop_") + "_Mesh"
        parent_to(mesh, empty)

    return altar_cell


def build_guardians(mats):
    """Low-poly skeletal guardians (hidden by the frontend, kept for parity).

    Geometry is authored around the origin and the object is placed on the cell,
    so the glTF node translation lands exactly on the grid cell centre.
    """
    altar_cell = find("Q")[0]
    ax = cell_center(altar_cell[0], altar_cell[1])[0]
    az = cell_center(altar_cell[0], altar_cell[1])[2]
    for c, r in find("E"):
        cx = cell_center(c, r)[0]
        cz = cell_center(c, r)[2]
        facing = math.atan2(-(az - cz), ax - cx)
        bone, metal = 0, 1
        bm = bmesh.new()

        def at(dx, y, dz):
            return (dx, y, dz)

        add_icosphere(bm, at(0, 2.1, 0), (0.22, 0.25, 0.22), bone)
        add_box(bm, at(0.09, 1.92, 0), (0.24, 0.1, 0.2), bone)
        add_cylinder(bm, at(0, 1.8, 0), 0.07, 0.07, 0.14, segments=6, material_index=bone, rotation=ROT_Z_TO_Y)
        for i in range(5):
            add_box(bm, at(0, 1.68 - i * 0.14, 0), (0.09, 0.1, 0.09), bone)
        for y in (1.58, 1.42):
            add_cylinder(bm, at(0, y, 0), 0.29, 0.29, 0.09, segments=10, material_index=bone,
                         rotation=ROT_Z_TO_Y, cap_ends=False)
        add_box(bm, at(0, 1.3, 0), (0.3, 0.13, 0.19), bone)
        for side in (-1, 1):
            add_icosphere(bm, at(0, 1.62, side * 0.33), (0.17, 0.14, 0.17), metal)
            add_cylinder(bm, at(0, 1.40, side * 0.39), 0.07, 0.07, 0.42, segments=6, material_index=bone, rotation=ROT_Z_TO_Y)
            add_cylinder(bm, at(0.05, 1.06, side * 0.39), 0.06, 0.06, 0.38, segments=6, material_index=bone, rotation=ROT_Z_TO_Y)
            add_box(bm, at(0.06, 0.84, side * 0.39), (0.12, 0.12, 0.1), bone)
            add_cylinder(bm, at(0, 0.96, side * 0.13), 0.085, 0.08, 0.58, segments=6, material_index=bone, rotation=ROT_Z_TO_Y)
            add_cylinder(bm, at(0, 0.42, side * 0.14), 0.08, 0.07, 0.52, segments=6, material_index=bone, rotation=ROT_Z_TO_Y)
            add_box(bm, (0.06, 0.08, side * 0.14), (0.26, 0.1, 0.14), bone)
        add_cylinder(bm, at(-0.16, 1.06, -0.5), 0.3, 0.3, 0.08, segments=10, material_index=metal,
                     rotation=Matrix.Rotation(math.radians(90), 4, "Y"))
        add_cylinder(bm, at(0.18, 1.25, 0.45), 0.05, 0.05, 0.3, segments=6, material_index=metal, rotation=ROT_Z_TO_Y)
        add_box(bm, at(0.18, 0.92, 0.45), (0.1, 0.38, 0.04), metal)

        ob = new_object(f"Enemy_{c}_{r}", bm, [mats["bone"], mats["metal"]])
        ob.location = cell_center(c, r, 0.0)
        ob.rotation_euler = (0.0, facing, 0.0)


# ---------------------------------------------------------------- puddles ---
def build_puddle_mesh(radius=1.15, seed=11):
    """An irregular shallow pool with a meniscus rim, lying on the floor.

    Origin sits at the centre so the frontend can scale/rotate clones freely.
    """
    rng = np.random.default_rng(seed)
    bm = bmesh.new()
    seg = 28
    rings = 5
    # irregular outline: radius wobbles with a couple of harmonics
    outline = []
    for i in range(seg):
        a = (i / seg) * math.tau
        wob = (1.0
               + 0.16 * math.sin(a * 2 + 0.7)
               + 0.10 * math.sin(a * 3 - 1.2)
               + 0.06 * math.sin(a * 5 + 2.4))
        outline.append(radius * wob)

    rows = []
    for r in range(rings + 1):
        t = r / rings
        row = []
        for i in range(seg):
            a = (i / seg) * math.tau
            rad = outline[i] * t
            # Dome in the middle, meniscus rising at the rim. Both terms are
            # >= 0 so the sheet never dips below its own plane - a negative rim
            # sinks into the floor slabs and z-fights into a black shard.
            y = 0.006 * math.sin(math.pi * t) + 0.012 * t ** 4
            x, z = math.cos(a) * rad, math.sin(a) * rad * 0.78
            x += rng.normal(0, 0.004) if 0 < t < 1 else 0
            z += rng.normal(0, 0.004) if 0 < t < 1 else 0
            row.append(bm.verts.new((x, y, z)))
        rows.append(row)

    for r in range(rings):
        for i in range(seg):
            j = (i + 1) % seg
            # Wound so the normal points +Y (up): the water is seen from above.
            bm.faces.new((rows[r][i], rows[r + 1][i], rows[r + 1][j], rows[r][j]))
    bm.normal_update()
    uv = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for loop in f.loops:
            co = loop.vert.co
            loop[uv].uv = (co.x / (radius * 2) + 0.5, co.z / (radius * 2) + 0.5)
    return bm


def export_puddle(mats, path=None):
    path = path or os.path.join(HERE, "puddle.glb")
    coll = bpy.data.collections.get("Water")
    if coll is None:
        coll = bpy.data.collections.new("Water")
        bpy.context.scene.collection.children.link(coll)
    old = bpy.data.objects.get("Puddle")
    if old:
        me_old = old.data
        bpy.data.objects.remove(old, do_unlink=True)
        if me_old.users == 0:
            bpy.data.meshes.remove(me_old)
    ob = bpy.data.objects.new("Puddle", bpy.data.meshes.new("Puddle"))
    coll.objects.link(ob)
    bm = build_puddle_mesh()
    ob.data = bpy.data.meshes.new("Puddle")
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.materials.append(mats["water_puddle"])
    ob.data.name = "Puddle"

    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    kwargs = dict(filepath=path, export_format="GLB", export_yup=True, export_apply=True,
                  use_selection=True, export_cameras=False, export_lights=False)
    try:
        bpy.ops.export_scene.gltf(**kwargs, export_image_format="WEBP")
    except TypeError:
        bpy.ops.export_scene.gltf(**kwargs)
    bpy.ops.object.select_all(action="DESELECT")
    return {"path": path, "bytes": os.path.getsize(path)}


# ------------------------------------------------------------- wall bake ----
def bake_wall_material(mat, walls_obj):
    """Medieval ashlar: 0.8 x 0.4 m blocks, per-block protrusion, damp base."""
    nt = mat.node_tree
    nt.nodes.clear()
    N = nt.nodes

    uvn = N.new("ShaderNodeUVMap"); uvn.uv_map = "UVMap"
    sep = N.new("ShaderNodeSeparateXYZ")
    nt.links.new(uvn.outputs["UV"], sep.inputs["Vector"])
    U, V = sep.outputs["X"], sep.outputs["Y"]

    def math2(op, a, b=None):
        n = N.new("ShaderNodeMath"); n.operation = op
        for i, val in enumerate((a, b)):
            if val is None:
                continue
            if isinstance(val, (int, float)):
                n.inputs[i].default_value = val
            else:
                nt.links.new(val, n.inputs[i])
        return n.outputs[0]

    def rgba(fac, a, b, blend="MIX"):
        m = N.new("ShaderNodeMix"); m.data_type = "RGBA"; m.blend_type = blend
        if isinstance(fac, (int, float)):
            m.inputs[0].default_value = fac
        else:
            nt.links.new(fac, m.inputs[0])
        for slot, val in ((6, a), (7, b)):
            if isinstance(val, tuple):
                m.inputs[slot].default_value = (*val, 1.0)
            else:
                nt.links.new(val, m.inputs[slot])
        return m.outputs[2]

    def fmix(fac, a, b):
        m = N.new("ShaderNodeMix"); m.data_type = "FLOAT"
        if isinstance(fac, (int, float)):
            m.inputs[0].default_value = fac
        else:
            nt.links.new(fac, m.inputs[0])
        for slot, val in ((2, a), (3, b)):
            if isinstance(val, (int, float)):
                m.inputs[slot].default_value = val
            else:
                nt.links.new(val, m.inputs[slot])
        return m.outputs[0]

    def maprange(val, f0, f1, t0, t1):
        n = N.new("ShaderNodeMapRange")
        if isinstance(val, (int, float)):
            n.inputs["Value"].default_value = val
        else:
            nt.links.new(val, n.inputs["Value"])
        n.inputs["From Min"].default_value = f0
        n.inputs["From Max"].default_value = f1
        n.inputs["To Min"].default_value = t0
        n.inputs["To Max"].default_value = t1
        return n.outputs["Result"]

    def periodic_noise(fx, fy, scale, detail):
        cu = math2("COSINE", math2("MULTIPLY", math2("MULTIPLY", U, float(fx)), 6.2831853))
        su = math2("SINE", math2("MULTIPLY", math2("MULTIPLY", U, float(fx)), 6.2831853))
        cv = math2("COSINE", math2("MULTIPLY", math2("MULTIPLY", V, float(fy)), 6.2831853))
        sv = math2("SINE", math2("MULTIPLY", math2("MULTIPLY", V, float(fy)), 6.2831853))
        comb = N.new("ShaderNodeCombineXYZ")
        nt.links.new(cu, comb.inputs[0]); nt.links.new(su, comb.inputs[1]); nt.links.new(cv, comb.inputs[2])
        n = N.new("ShaderNodeTexNoise"); n.noise_dimensions = "4D"
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = 0.55
        nt.links.new(comb.outputs["Vector"], n.inputs["Vector"])
        nt.links.new(sv, n.inputs["W"])
        return n.outputs["Fac"]

    def white(x, y, w):
        comb = N.new("ShaderNodeCombineXYZ")
        nt.links.new(x, comb.inputs[0]); nt.links.new(y, comb.inputs[1])
        comb.inputs[2].default_value = w
        wn = N.new("ShaderNodeTexWhiteNoise"); wn.noise_dimensions = "3D"
        nt.links.new(comb.outputs["Vector"], wn.inputs["Vector"])
        return wn.outputs["Value"]

    # 0.8 x 0.4 m blocks -> 0.2 x 0.1 in UV (5 x 10 per 4 m tile)
    BW, RH = 0.20, 0.10
    brick = N.new("ShaderNodeTexBrick")
    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Mortar Size"].default_value = 0.0045
    brick.inputs["Mortar Smooth"].default_value = 0.0025
    brick.inputs["Brick Width"].default_value = BW
    brick.inputs["Row Height"].default_value = RH
    brick.offset = 0.5
    brick.offset_frequency = 2
    brick.squash = 1.0
    nt.links.new(uvn.outputs["UV"], brick.inputs["Vector"])
    mask = math2("SUBTRACT", 1.0, brick.outputs["Fac"])   # 1 on brick, 0 on mortar

    rowR = math2("FLOOR", math2("MULTIPLY", V, 1.0 / RH))
    shift = math2("MULTIPLY", math2("MODULO", rowR, 2.0), BW * 0.5)
    bx = math2("FLOOR", math2("DIVIDE", math2("SUBTRACT", U, shift), BW))
    bx5 = math2("MODULO", bx, 5.0)
    row10 = math2("MODULO", rowR, 10.0)

    v1 = white(bx5, row10, 3.7)
    v2 = white(bx5, row10, 9.1)
    v3 = white(bx5, row10, 15.3)

    # base colour: block tones with a wide range (some blocks much darker),
    # weathered by seamless stains and vertical streaks
    stain = maprange(periodic_noise(1, 1, 2.4, 6), 0.32, 0.68, 0.72, 1.05)
    streak = maprange(periodic_noise(4, 1, 2.2, 4), 0.35, 0.65, 0.82, 1.02)
    block_a = rgba(v2, (0.235, 0.222, 0.196), (0.565, 0.536, 0.478))
    block_a = rgba(1.0, block_a, stain, "MULTIPLY")
    block_a = rgba(1.0, block_a, streak, "MULTIPLY")
    scalar = maprange(v1, 0.2, 0.85, 0.74, 1.24)
    tint = N.new("ShaderNodeCombineColor")
    for i in range(3):
        nt.links.new(scalar, tint.inputs[i])
    brick_col = rgba(1.0, block_a, tint.outputs["Color"], "MULTIPLY")
    mortar_col = rgba(periodic_noise(3, 3, 5.0, 3), (0.045, 0.042, 0.038), (0.092, 0.085, 0.076))
    base_col = rgba(mask, mortar_col, brick_col)

    # damp grime rising off the floor (object-space Y: the dungeon is Y-up)
    objcoord = N.new("ShaderNodeTexCoord")
    osep = N.new("ShaderNodeSeparateXYZ")
    nt.links.new(objcoord.outputs["Object"], osep.inputs["Vector"])
    damp = maprange(osep.outputs["Y"], 0.05, 0.55, 0.58, 1.0)
    damped = rgba(1.0, base_col, damp, "MULTIPLY")
    # and a faint green cast where the stone stays wet
    mossy = rgba(maprange(osep.outputs["Y"], 0.02, 0.40, 0.35, 0.0), base_col,
                 (0.55, 0.62, 0.42), "MIX")
    base_col = rgba(maprange(osep.outputs["Y"], 0.02, 0.40, 1.0, 0.0), damped, mossy, "MIX")

    # roughness: rough mortar, smoother worn block faces
    grit = periodic_noise(12, 12, 9.0, 4)
    r_brick = maprange(grit, 0.2, 0.8, 0.38, 0.68)
    rough = fmix(mask, 0.95, r_brick)

    # bump: mortar recess + per-block depth variation + fine grit
    bump_blocks = fmix(v3, -0.35, 0.45)
    bump_a = N.new("ShaderNodeBump")
    bump_a.inputs["Strength"].default_value = 0.62
    bump_a.inputs["Distance"].default_value = 0.03
    nt.links.new(fmix(mask, -1.0, bump_blocks), bump_a.inputs["Height"])
    bump_b = N.new("ShaderNodeBump")
    bump_b.inputs["Strength"].default_value = 0.20
    bump_b.inputs["Distance"].default_value = 0.004
    nt.links.new(grit, bump_b.inputs["Height"])
    nt.links.new(bump_a.outputs["Normal"], bump_b.inputs["Normal"])

    bsdf = N.new("ShaderNodeBsdfPrincipled")
    nt.links.new(base_col, bsdf.inputs["Base Color"])
    nt.links.new(rough, bsdf.inputs["Roughness"])
    nt.links.new(bump_b.outputs["Normal"], bsdf.inputs["Normal"])
    out = N.new("ShaderNodeOutputMaterial")
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return {"nodes": len(N)}


def bake_textures(mat, obj, tag="wall"):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = 2
    scene.cycles.use_denoising = False
    scene.render.bake.margin = 8

    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    nt = mat.node_tree
    N = nt.nodes

    def bake_pass(img, bake_type):
        n = N.new("ShaderNodeTexImage")
        n.image = img
        for nn in N:
            nn.select = False
        n.select = True
        N.active = n
        bpy.ops.object.bake(type=bake_type, pass_filter={"COLOR"} if bake_type == "DIFFUSE" else set())
        N.remove(n)

    for im in [i for i in bpy.data.images if i.name.startswith(f"{tag}_")]:
        bpy.data.images.remove(im)

    base = bpy.data.images.new(f"{tag}_basecolor", 2048, 2048, alpha=False)
    base.colorspace_settings.name = "sRGB"
    bake_pass(base, "DIFFUSE")
    base.filepath_raw = os.path.join(TEX, f"{tag}_basecolor.png")
    base.file_format = "PNG"
    base.save()

    norm = bpy.data.images.new(f"{tag}_normal", 2048, 2048, alpha=False)
    norm.colorspace_settings.name = "Non-Color"
    bake_pass(norm, "NORMAL")
    norm.filepath_raw = os.path.join(TEX, f"{tag}_normal.png")
    norm.file_format = "PNG"
    norm.save()

    rough = bpy.data.images.new(f"{tag}_rough", 1024, 1024, alpha=False)
    rough.colorspace_settings.name = "Non-Color"
    bake_pass(rough, "ROUGHNESS")
    rough.filepath_raw = os.path.join(TEX, f"{tag}_rough.png")
    rough.file_format = "PNG"
    rough.save()

    rp = np.empty(1024 * 1024 * 4, dtype=np.float32)
    rough.pixels.foreach_get(rp)
    orm = np.ones(1024 * 1024 * 4, dtype=np.float32)
    orm[1::4] = rp[1::4]
    orm[2::4] = 0.0
    orm_img = bpy.data.images.new(f"{tag}_orm", 1024, 1024, alpha=False)
    orm_img.colorspace_settings.name = "Non-Color"
    orm_img.pixels.foreach_set(orm)
    orm_img.filepath_raw = os.path.join(TEX, f"{tag}_orm.png")
    orm_img.file_format = "PNG"
    orm_img.save()

    for im in (base, norm, orm_img):
        im.pack()

    # swap to the baked-image material for export
    nt.nodes.clear()
    N = nt.nodes

    def img_node(img):
        n = N.new("ShaderNodeTexImage")
        n.image = img
        return n

    bsdf = N.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Metallic"].default_value = 0.0
    out = N.new("ShaderNodeOutputMaterial")
    bc = img_node(base)
    nt.links.new(bc.outputs["Color"], bsdf.inputs["Base Color"])
    nm = img_node(norm)
    nmap = N.new("ShaderNodeNormalMap")
    nt.links.new(nm.outputs["Color"], nmap.inputs["Color"])
    nt.links.new(nmap.outputs["Normal"], bsdf.inputs["Normal"])
    orm_n = img_node(orm_img)
    sep = N.new("ShaderNodeSeparateColor")
    nt.links.new(orm_n.outputs["Color"], sep.inputs["Color"])
    nt.links.new(sep.outputs["Green"], bsdf.inputs["Roughness"])
    nt.links.new(sep.outputs["Blue"], bsdf.inputs["Metallic"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return {"basecolor": base.name, "normal": norm.name, "orm": orm_img.name}


# ------------------------------------------------------------------ export --
def glb_summary(path):
    with open(path, "rb") as f:
        data = f.read()
    ln = struct.unpack_from("<I", data, 12)[0]
    js = json.loads(data[20:20 + ln].decode("utf-8"))
    return {
        "bytes": len(data),
        "nodes": len(js.get("nodes", [])),
        "meshes": [m.get("name") for m in js.get("meshes", [])],
        "materials": [m.get("name") for m in js.get("materials", [])],
        "has_color_attr": any("COLOR_0" in (p.get("attributes") or {})
                              for m in js.get("meshes", []) for p in m.get("primitives", [])),
    }


def export_level(path=None):
    path = path or os.path.join(HERE, "dungeon.glb")
    coll = bpy.data.collections["Dungeon"]
    bpy.ops.object.select_all(action="DESELECT")
    for ob in coll.objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = next(o for o in coll.objects)
    kwargs = dict(filepath=path, export_format="GLB", export_yup=True, export_apply=True,
                  use_selection=True, export_cameras=False, export_lights=False,
                  export_materials="EXPORT", export_extras=True)
    try:
        bpy.ops.export_scene.gltf(**kwargs, export_image_format="WEBP")
        fmt = "WEBP"
    except TypeError:
        bpy.ops.export_scene.gltf(**kwargs)
        fmt = "PNG"
    return glb_summary(path), fmt


def reset_dungeon():
    existing = bpy.data.collections.get("Dungeon")
    if existing is not None:
        for ob in list(existing.objects):
            data = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            if isinstance(data, bpy.types.Mesh) and data.users == 0:
                bpy.data.meshes.remove(data)
        bpy.data.collections.remove(existing)
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    coll = bpy.data.collections.new("Dungeon")
    bpy.context.scene.collection.children.link(coll)
    return coll


def main():
    validate()

    reset_dungeon()
    mats = build_materials()

    walls, wall_cells = build_walls(mats)
    floor = build_floor(mats)
    ceiling = build_ceiling(mats)
    altar_cell = build_props(mats)
    build_guardians(mats)

    # Replace the placeholder prop geometry with the modelled props (torch
    # sconces, braziers, altar, lectern, scattered remains). Runs after the
    # marker empties exist, because the props parent onto them.
    import build_props as props_mod
    props_mod.main()

    torches = torch_cells()
    ao_stats = {}
    for name, ob in (("Walls", walls), ("Floor", floor), ("Ceiling", ceiling)):
        ao_stats[name] = bake_vertex_light(ob, torches, altar_cell)

    bake_wall_material(mats["stone_wall"], walls)
    baked = bake_textures(mats["stone_wall"], walls, tag="wall")

    puddle = export_puddle(mats)
    summary, fmt = export_level()
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "dungeon.blend"))

    result = {
        "cell": CELL,
        "grid": [W, H],
        "world_size": [W * CELL, H * CELL],
        "wall_cells": len(wall_cells),
        "floor_verts": len(floor.data.vertices),
        "ceiling_verts": len(ceiling.data.vertices),
        "wall_tris": sum(len(p.vertices) - 2 for p in walls.data.polygons),
        "ao": ao_stats,
        "baked": baked,
        "puddle": puddle,
        "image_format": fmt,
        "glb": summary,
        "texture_files": {f: os.path.getsize(os.path.join(TEX, f))
                          for f in os.listdir(TEX) if f.startswith("wall_")},
    }
    with open(os.path.join(HERE, "level_result.json"), "w") as f:
        json.dump(result, f, indent=1, default=str)
    print("LEVEL RESULT", json.dumps(result, indent=1, default=str))


if __name__ == "__main__":
    main()