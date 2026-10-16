"""Realistic dungeon props for the Knowledge Dungeon level.

AXIS CONVENTION - read this before touching anything below.
The dungeon is authored **Y-up**: the floor is a thin slab in Y (0.1 m), the
walls are 3 m along Y, and Blender's Y-up is exported to glTF's Y-up unchanged.
But `bmesh.ops.create_cone` / `create_cube` / `create_icosphere` all build along
**Z**. So every "standing" primitive here passes UP to stand it up. Getting this
wrong silently produces props lying on their side, which is exactly the class of
bug that is invisible in a bbox test and obvious in a render.

Design intent (why these shapes, not just boxes):
  * A torch has to read as *iron + wood + fire*: a back plate bolted to the
    stone, a forged arm sweeping out and up, a charred log held in a cage of
    ribs, and the flame sitting in the cage. The silhouette against fog is the
    only thing most players ever see of it.
  * Braziers are life markers, so they get a tall tripod with cross braces and a
    deep bowl - readable from across a hall.
  * The altar is the goal, so it steps up: plinths, a fluted column, a chamfered
    cap, and the crystal floating clear of it.
  * The lectern is stone, not furniture: heavy base, collar, raked desk, open
    book.
  * Remains are deliberately *broken* - a half-buried skull, splayed ribs, loose
    long bones. A tidy skeleton reads as a prop; a scattered one reads as a
    death.

Run headless (rebuilds the props inside the current scene):
    blender --background dungeon/dungeon.blend --python dungeon/build_props.py
"""

import math
import os
import random

import bmesh
import bpy
from mathutils import Euler, Matrix, Vector

# Blender primitives are Z-up; the dungeon is Y-up. This stands them up.
# -90 deg, not +90: +90 maps the primitive's +Z onto world -Y, which turns every
# asymmetric part upside down (flames pointing into the bowl, a sconce log
# hanging below its own bracket).
UP = Matrix.Rotation(-math.pi / 2, 4, "X")
TAU = math.pi * 2


# ------------------------------------------------------------------ helpers --
def coll():
    return bpy.data.collections.get("Dungeon")


def new_object(name, bm, materials):
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    for m in materials:
        me.materials.append(m)
    ob = bpy.data.objects.new(name, me)
    coll().objects.link(ob)
    return ob


def parent_to(child, parent):
    """Parent without moving the child.

    Prop geometry is authored in world coordinates, so the inverse has to be set
    or the parent's transform is applied on top and every prop lands at twice
    its intended position.
    """
    child.parent = parent
    child.matrix_parent_inverse = parent.matrix_world.inverted()
    return child


def _tag_faces(bm, verts, material_index):
    faces = set()
    for v in verts:
        faces.update(v.link_faces)
    for f in faces:
        f.material_index = material_index


def add_box(bm, center, size, material_index=0, rotation=None):
    m = Matrix.Translation(Vector(center)) @ Matrix.Diagonal(Vector((*size, 1.0)))
    if rotation is not None:
        m = m @ rotation
    res = bmesh.ops.create_cube(bm, size=1.0, matrix=m, calc_uvs=True)
    _tag_faces(bm, res["verts"], material_index)


def add_cylinder(bm, center, r_bottom, r_top, depth, segments=12, material_index=0,
                 rotation=None, cap_ends=True):
    """Cylinder/cone along local Z unless `rotation` says otherwise.

    Pass UP for anything standing on the floor.
    """
    m = Matrix.Translation(Vector(center))
    if rotation is not None:
        m = m @ rotation
    res = bmesh.ops.create_cone(bm, cap_ends=cap_ends, cap_tris=False, segments=segments,
                                radius1=r_bottom, radius2=r_top, depth=depth,
                                matrix=m, calc_uvs=True)
    _tag_faces(bm, res["verts"], material_index)


def add_sphere(bm, center, scale, material_index=0, subdivisions=2, rotation=None):
    m = Matrix.Translation(Vector(center)) @ Matrix.Diagonal(Vector((*scale, 1.0)))
    if rotation is not None:
        m = m @ rotation
    res = bmesh.ops.create_icosphere(bm, subdivisions=subdivisions, radius=1.0,
                                     matrix=m, calc_uvs=True)
    _tag_faces(bm, res["verts"], material_index)


def add_beveled_box(bm, center, size, material_index=0, bevel=0.02, segments=1,
                    rotation=None):
    """Box with real chamfered edges - the single biggest 'not a primitive' win."""
    m = Matrix.Translation(Vector(center)) @ Matrix.Diagonal(Vector((*size, 1.0)))
    if rotation is not None:
        m = m @ rotation
    res = bmesh.ops.create_cube(bm, size=1.0, matrix=m, calc_uvs=True)
    # Tag before beveling: the op rebuilds these verts, so the handles go stale.
    _tag_faces(bm, res["verts"], material_index)
    edges = [e for e in bm.edges if all(v in res["verts"] for v in e.verts)]
    bmesh.ops.bevel(bm, geom=edges, offset=bevel, segments=segments,
                    affect="EDGES", profile=0.5, clamp_overlap=True,
                    material=-1)  # -1: chamfer faces inherit their source material


def add_poly_tube(bm, points, radius, material_index=0, sides=6):
    """Low-poly swept tube through a polyline - iron arms, ribs, cage staves.

    Hand-rolled rather than bmesh.ops.spin: we need a specific radius and
    consistent material tagging, and this stays predictable across versions.
    """
    if len(points) < 2:
        return
    rings = []
    up = Vector((0, 1, 0))
    for i, p in enumerate(points):
        p = Vector(p)
        if i == 0:
            tangent = (Vector(points[1]) - p).normalized()
        elif i == len(points) - 1:
            tangent = (p - Vector(points[i - 1])).normalized()
        else:
            tangent = (Vector(points[i + 1]) - Vector(points[i - 1])).normalized()
        ref = up if abs(tangent.dot(up)) < 0.95 else Vector((1, 0, 0))
        n1 = tangent.cross(ref).normalized()
        n2 = tangent.cross(n1).normalized()
        rings.append([bm.verts.new(p + (n1 * math.cos(TAU * s / sides)
                                        + n2 * math.sin(TAU * s / sides)) * radius)
                      for s in range(sides)])
    for i in range(len(rings) - 1):
        for s in range(sides):
            t = (s + 1) % sides
            try:
                f = bm.faces.new((rings[i][s], rings[i][t], rings[i + 1][t], rings[i + 1][s]))
                f.material_index = material_index
            except ValueError:
                pass
    for ring, flip in ((rings[0], True), (rings[-1], False)):
        try:
            f = bm.faces.new(tuple(reversed(ring)) if flip else tuple(ring))
            f.material_index = material_index
        except ValueError:
            pass


def add_bone(bm, start, end, radius, material_index=0, sides=6):
    """A long bone between two points, with swollen ends."""
    a, b = Vector(start), Vector(end)
    add_poly_tube(bm, [tuple(a), tuple(b)], radius, material_index=material_index, sides=sides)
    for p in (a, b):
        add_sphere(bm, p, (radius * 1.55, radius * 1.55, radius * 1.55),
                   material_index=material_index, subdivisions=1)


# ---------------------------------------------------------------- materials --
def ensure_materials():
    """Ensure the prop material set exists AND matches the values in this file.

    Rebuilt in place every run: this used to create-when-missing only, so once
    a dungeon.blend was made with older (near-black) values, no amount of
    tweaking the numbers here could reach the file - the stale datablock won
    every rebuild. Always setting the inputs now is what makes the .blend the
    *output* of this code rather than a cache of past mistakes.

    Returns the full mapping, so repeated builds in one session are safe.
    """
    names = {}

    def principled(name, base, rough, metallic=0.0):
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        mat.use_nodes = True
        nt = mat.node_tree
        # A planar rebuild beats in-place tweaks: the tree can carry remnants of
        # an older author (image textures, emission chains), and this runs once
        # per build, not per frame.
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        bsdf.inputs["Base Color"].default_value = (*base, 1.0)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metallic
        names[name] = mat
        return mat

    def emissive(name, color, strength):
        mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        mat.use_nodes = True
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (*color, 1.0)
        em.inputs["Strength"].default_value = strength
        nt.links.new(em.outputs["Emission"], out.inputs["Surface"])
        names[name] = mat
        return mat

    # Colour matters more than usual here: the dungeon is lit by a handful of
    # torches against near-black stone, so a physically "correct" near-black
    # iron (0.05 base, metalness 0.85) has nothing to reflect and renders as a
    # black cut-out. These are lifted deliberately, and the metals keep some
    # diffuse so they still catch a rim of torchlight.
    principled("prop_iron", (0.29, 0.30, 0.35), 0.45, 0.55)
    principled("prop_iron_rust", (0.38, 0.21, 0.12), 0.70, 0.35)
    principled("prop_wood", (0.32, 0.20, 0.11), 0.78)
    principled("prop_charred", (0.10, 0.085, 0.075), 0.88)
    principled("prop_bone", (0.74, 0.70, 0.58), 0.62)
    principled("prop_parchment", (0.60, 0.53, 0.39), 0.82)
    principled("prop_stone", (0.44, 0.42, 0.48), 0.76)
    emissive("prop_flame", (1.0, 0.42, 0.12), 9.0)
    emissive("prop_ember", (1.0, 0.22, 0.05), 3.2)
    emissive("prop_crystal", (0.62, 0.30, 1.0), 6.0)

    return {
        "iron": names["prop_iron"],
        "iron_rust": names["prop_iron_rust"],
        "wood": names["prop_wood"],
        "char": names["prop_charred"],
        "bone": names["prop_bone"],
        "parchment": names["prop_parchment"],
        "stone": names["prop_stone"],
        "flame": names["prop_flame"],
        "ember": names["prop_ember"],
        "crystal": names["prop_crystal"],
    }


# ------------------------------------------------------------- torch sconce --
def build_torch_sconce(name, mats, location, facing):
    """Wall bracket + charred log + iron cage + flame.

    Built in a local frame where +Z is up, then stood up with UP and finally
    swung to face out of the wall. `facing` is the out-from-wall angle in
    radians about Y (0 = +Z, PI/2 = +X).
    """
    bm = bmesh.new()
    # Ry(facing) @ UP, not UP @ Ry: the world-space swing about Y has to be
    # applied AFTER standing the local frame up, and the two do not commute.
    # The extra half-turn: the local body extends along -Z into enumeration
    # (measured on real sconces - only a ~13 cm sliver cleared the wall face),
    # so mapping "out from the wall" needs the reversal to honour the facing
    # contract; without it every flush-mounted torch hangs inside the block.
    base = Matrix.Rotation(facing + math.pi, 4, "Y") @ UP

    def at(x, y, z):
        p = base @ Vector((x, y, z)) + Vector(location)
        return (p.x, p.y, p.z)

    def cyl(x, y, z, r0, r1, depth, mi=0, segments=8):
        add_cylinder(bm, at(x, y, z), r0, r1, depth, segments=segments,
                     material_index=mi, rotation=base)

    # back plate bolted flat to the stone
    add_box(bm, at(0, 0, 0.03), (0.17, 0.32, 0.05), 0, rotation=base)
    for bx in (-0.055, 0.055):
        for by in (-0.11, 0.11):
            cyl(bx, by, 0.06, 0.017, 0.017, 0.022, mi=0, segments=6)

    # forged arm: plate -> elbow -> up and out to the cage
    add_poly_tube(bm, [at(0, 0, 0.05), at(0, -0.03, 0.15),
                       at(0, 0.05, 0.22), at(0, 0.17, 0.21)],
                  0.023, material_index=0, sides=6)
    add_sphere(bm, at(0, 0.10, 0.215), (0.035, 0.035, 0.035), material_index=0,
               subdivisions=1)

    # charred log held in the cage
    cyl(0, 0.17, 0.32, 0.044, 0.038, 0.30, mi=1, segments=8)
    cyl(0, 0.17, 0.49, 0.036, 0.018, 0.10, mi=2, segments=7)

    # cage: staves sweeping up around the flame, plus top and bottom collars
    for i in range(5):
        a = TAU * i / 5 + 0.3
        rx, ry = math.cos(a) * 0.085, math.sin(a) * 0.085
        add_poly_tube(bm, [at(rx, 0.17 + ry, 0.35),
                           at(rx * 1.15, 0.17 + ry * 1.15, 0.55),
                           at(rx * 0.45, 0.17 + ry * 0.45, 0.62)],
                      0.013, material_index=0, sides=5)
    cyl(0, 0.17, 0.635, 0.062, 0.048, 0.035, mi=0, segments=10)
    cyl(0, 0.17, 0.335, 0.076, 0.062, 0.028, mi=0, segments=10)

    return new_object(name, bm, [mats["iron"], mats["wood"], mats["char"]])


def build_torch_flame(name, mats, location, facing):
    """Fire sitting in the sconce cage."""
    bm = bmesh.new()
    # Same half-turn as the sconce (see its comment): the un-reversed frame
    # swings the flame into the wall block instead of out over the cage.
    base = Matrix.Rotation(facing + math.pi, 4, "Y") @ UP
    p = base @ Vector((0, 0.17, 0.52)) + Vector(location)
    add_cylinder(bm, tuple(p), 0.055, 0.0, 0.22, segments=8, material_index=0,
                 rotation=base)
    add_sphere(bm, (p.x, p.y + 0.10, p.z), (0.045, 0.05, 0.045),
               material_index=1, subdivisions=1)
    return new_object(name, bm, [mats["flame"], mats["ember"]])


def build_torch_stand(name, mats, location):
    """Free-standing torch for the open-hall cells with no wall to mount on.

    Same iron-and-fire language as the sconce (cage, coals, flame) on a slim
    tripod, so a player reads it as the same object family rather than a pole.
    """
    bm = bmesh.new()
    cx, cy, cz = location

    for i in range(3):
        a = TAU * i / 3 + 0.5
        dx, dz = math.cos(a), math.sin(a)
        add_poly_tube(bm, [
            (cx + dx * 0.26, cy + 0.02, cz + dz * 0.26),
            (cx + dx * 0.13, cy + 0.36, cz + dz * 0.13),
            (cx + dx * 0.05, cy + 1.22, cz + dz * 0.05),
        ], 0.026, material_index=0, sides=6)
        add_box(bm, (cx + dx * 0.26, cy + 0.015, cz + dz * 0.26), (0.11, 0.03, 0.11),
                material_index=1)

    # collar, basket and rim, all standing on the dungeon floor
    add_cylinder(bm, (cx, cy + 1.25, cz), 0.10, 0.13, 0.07, segments=10,
                 material_index=0, rotation=UP)
    add_cylinder(bm, (cx, cy + 1.42, cz), 0.14, 0.22, 0.26, segments=12,
                 material_index=0, rotation=UP)
    for i in range(6):
        a = TAU * i / 6
        add_poly_tube(bm, [
            (cx + math.cos(a) * 0.14, cy + 1.36, cz + math.sin(a) * 0.14),
            (cx + math.cos(a) * 0.23, cy + 1.52, cz + math.sin(a) * 0.23),
            (cx + math.cos(a) * 0.17, cy + 1.61, cz + math.sin(a) * 0.17),
        ], 0.013, material_index=0, sides=5)
    add_cylinder(bm, (cx, cy + 1.62, cz), 0.22, 0.19, 0.04, segments=12,
                 material_index=0, rotation=UP)

    return new_object(name, bm, [mats["iron"], mats["iron_rust"]])


def build_torch_stand_flame(name, mats, location):
    bm = bmesh.new()
    cx, cy, cz = location
    add_cylinder(bm, (cx, cy + 1.70, cz), 0.13, 0.0, 0.34, segments=8,
                 material_index=0, rotation=UP)
    add_sphere(bm, (cx, cy + 1.78, cz), (0.11, 0.14, 0.11), material_index=1,
               subdivisions=1)
    for i in range(5):
        a = TAU * i / 5
        add_sphere(bm, (cx + math.cos(a) * 0.11, cy + 1.47, cz + math.sin(a) * 0.11),
                   (0.05, 0.04, 0.05), material_index=1, subdivisions=1)
    return new_object(name, bm, [mats["flame"], mats["ember"]])


# ----------------------------------------------------------------- brazier --
def build_brazier(name, mats, location):
    """Life brazier: tall tripod, deep forged bowl, coals, flame."""
    bm = bmesh.new()
    cx, cy, cz = location

    for i in range(3):
        a = TAU * i / 3 + 0.4
        dx, dz = math.cos(a), math.sin(a)
        add_poly_tube(bm, [
            (cx + dx * 0.30, cy + 0.02, cz + dz * 0.30),
            (cx + dx * 0.17, cy + 0.42, cz + dz * 0.17),
            (cx + dx * 0.10, cy + 0.88, cz + dz * 0.10),
        ], 0.028, material_index=0, sides=6)
        add_box(bm, (cx + dx * 0.30, cy + 0.015, cz + dz * 0.30), (0.12, 0.03, 0.12),
                material_index=1)

    for i in range(3):
        a = TAU * i / 3 + 0.4
        b = TAU * (i + 1) / 3 + 0.4
        mid = (a + b) / 2
        add_poly_tube(bm, [
            (cx + math.cos(a) * 0.15, cy + 0.36, cz + math.sin(a) * 0.15),
            (cx + math.cos(mid) * 0.17, cy + 0.42, cz + math.sin(mid) * 0.17),
            (cx + math.cos(b) * 0.15, cy + 0.36, cz + math.sin(b) * 0.15),
        ], 0.014, material_index=0, sides=5)

    # bowl: near-vertical walls so it reads as a fire bowl, not a lampshade
    add_cylinder(bm, (cx, cy + 0.95, cz), 0.30, 0.42, 0.32, segments=14,
                 material_index=0, rotation=UP)
    add_cylinder(bm, (cx, cy + 1.11, cz), 0.45, 0.44, 0.06, segments=14,
                 material_index=0, rotation=UP, cap_ends=False)
    add_cylinder(bm, (cx, cy + 1.02, cz), 0.38, 0.22, 0.28, segments=14,
                 material_index=2, rotation=UP, cap_ends=False)
    add_cylinder(bm, (cx, cy + 0.80, cz), 0.12, 0.12, 0.18, segments=8,
                 material_index=0, rotation=UP)

    return new_object(name, bm, [mats["iron"], mats["iron_rust"], mats["char"]])


def build_brazier_fire(name, mats, location):
    bm = bmesh.new()
    cx, cy, cz = location
    for i, (dx, dz, s) in enumerate(((-0.12, 0.05, 0.9), (0.10, -0.06, 0.75),
                                    (0.02, 0.12, 1.05))):
        add_cylinder(bm, (cx + dx, cy + 1.10, cz + dz), 0.09 * s, 0.0, 0.34 * s,
                     segments=7, material_index=0,
                     rotation=UP @ Euler((0.12 * i, 0.0, 0.1 * i)).to_matrix().to_4x4())
    for i in range(6):
        a = TAU * i / 6
        add_sphere(bm, (cx + math.cos(a) * 0.17, cy + 0.96, cz + math.sin(a) * 0.17),
                   (0.06, 0.05, 0.05), material_index=1, subdivisions=1)
    return new_object(name, bm, [mats["flame"], mats["ember"]])


# ------------------------------------------------------------------- altar --
def build_altar(name, mats, location, crystal_height):
    """Stepped altar: plinths, a fluted column, a chamfered cap."""
    bm = bmesh.new()
    cx, cy, cz = location

    add_beveled_box(bm, (cx, cy + 0.08, cz), (1.50, 0.16, 1.50), material_index=0, bevel=0.03)
    add_beveled_box(bm, (cx, cy + 0.30, cz), (1.24, 0.30, 1.24), material_index=0, bevel=0.035)
    add_beveled_box(bm, (cx, cy + 0.53, cz), (1.02, 0.18, 1.02), material_index=0, bevel=0.03)

    # fluted column standing on the top step
    add_cylinder(bm, (cx, cy + 0.92, cz), 0.28, 0.24, 0.60, segments=12,
                 material_index=0, rotation=UP)
    for i in range(8):
        a = TAU * i / 8
        add_cylinder(bm, (cx + math.cos(a) * 0.27, cy + 0.92, cz + math.sin(a) * 0.27),
                     0.033, 0.033, 0.58, segments=5, material_index=1, rotation=UP)
    add_cylinder(bm, (cx, cy + 1.25, cz), 0.31, 0.31, 0.09, segments=12,
                 material_index=1, rotation=UP)

    # cap with a chamfer and a recessed offering plate
    add_beveled_box(bm, (cx, cy + 1.38, cz), (0.86, 0.15, 0.86), material_index=0, bevel=0.025)
    add_cylinder(bm, (cx, cy + 1.48, cz), 0.28, 0.24, 0.06, segments=12,
                 material_index=1, rotation=UP)

    # carved relief panels on the four plinth faces: thin axis points outward
    for i in range(4):
        a = TAU * i / 4 + math.pi / 4
        add_beveled_box(bm, (cx + math.cos(a) * 0.60, cy + 0.30, cz + math.sin(a) * 0.60),
                        (0.05, 0.18, 0.15), material_index=1, bevel=0.01,
                        rotation=Matrix.Rotation(math.pi / 2 - a, 4, "Y"))

    return new_object(name, bm, [mats["stone"], mats["iron_rust"]])


def build_altar_crystal(name, mats, location, crystal_height):
    bm = bmesh.new()
    cx, cy, cz = location
    h = crystal_height
    add_cylinder(bm, (cx, cy + h, cz), 0.10, 0.13, 0.20, segments=6,
                 material_index=1, rotation=UP)
    add_cylinder(bm, (cx, cy + h + 0.26, cz), 0.16, 0.0, 0.36, segments=6,
                 material_index=0, rotation=UP)
    add_cylinder(bm, (cx, cy + h - 0.16, cz), 0.11, 0.16, 0.22, segments=6,
                 material_index=0, rotation=UP @ Matrix.Rotation(math.pi, 4, "X"))
    for dx, dz, dy, s in ((0.10, 0.05, 0.16, 0.055), (-0.08, -0.07, 0.05, 0.042),
                          (0.02, -0.10, 0.24, 0.038)):
        add_sphere(bm, (cx + dx, cy + h + dy, cz + dz), (s, s * 1.6, s),
                   material_index=1, subdivisions=1)
    return new_object(name, bm, [mats["crystal"], mats["ember"]])


# ----------------------------------------------------------------- lectern --
def build_lectern(name, mats, location):
    """Stone lectern: heavy base, collar, raked desk with an open book."""
    bm = bmesh.new()
    cx, cy, cz = location
    # a box tipped about X so its face looks up at the player
    rake = Matrix.Rotation(math.radians(26), 4, "X")

    add_beveled_box(bm, (cx, cy + 0.07, cz), (0.84, 0.14, 0.84), material_index=0, bevel=0.025)
    add_beveled_box(bm, (cx, cy + 0.21, cz), (0.64, 0.18, 0.64), material_index=0, bevel=0.02)
    add_cylinder(bm, (cx, cy + 0.35, cz), 0.19, 0.15, 0.12, segments=10,
                 material_index=0, rotation=UP)
    add_cylinder(bm, (cx, cy + 0.72, cz), 0.105, 0.09, 0.64, segments=10,
                 material_index=0, rotation=UP)
    add_cylinder(bm, (cx, cy + 1.06, cz), 0.16, 0.14, 0.10, segments=10,
                 material_index=1, rotation=UP)

    add_beveled_box(bm, (cx, cy + 1.16, cz), (0.70, 0.07, 0.54), material_index=0,
                    bevel=0.015, rotation=rake)
    add_beveled_box(bm, (cx, cy + 1.12, cz + 0.21), (0.70, 0.09, 0.07), material_index=1,
                    bevel=0.012, rotation=rake)

    for sign in (-1, 1):
        leaf = rake @ Matrix.Rotation(sign * math.radians(8), 4, "Z")
        add_beveled_box(bm, (cx + sign * 0.155, cy + 1.215, cz + 0.005),
                        (0.29, 0.03, 0.40), material_index=2, bevel=0.008, rotation=leaf)

    return new_object(name, bm, [mats["stone"], mats["iron_rust"], mats["parchment"]])


# ---------------------------------------------------------------- skeleton --
def build_remains(name, mats, location, seed=0, variant=0):
    """Scattered bones. `variant` picks the arrangement so copies read as
    different deaths, not the same pile stamped out."""
    rnd = random.Random(seed * 977 + variant * 31 + 7)
    bm = bmesh.new()
    cx, cy, cz = location
    rot = Matrix.Rotation(rnd.uniform(0, TAU), 4, "Y")

    def at(x, y, z):
        p = rot @ Vector((x, y, z)) + Vector((cx, cy, cz))
        return (p.x, p.y, p.z)

    def loose(count=4, spread=0.34):
        for _ in range(count):
            a, b = TAU * rnd.random(), rnd.uniform(0.2, 0.36)
            add_bone(bm, at(rnd.uniform(-spread, spread), 0.02,
                            rnd.uniform(-spread, spread)),
                     at(rnd.uniform(-spread, spread), 0.02,
                        rnd.uniform(-spread, spread) + b),
                     0.022, material_index=0, sides=5)

    if variant % 3 == 0:
        # half-buried skull, jaw cracked open
        add_sphere(bm, at(0, 0.13, 0.0), (0.11, 0.12, 0.11), material_index=0,
                   subdivisions=2, rotation=rot @ Matrix.Rotation(0.4, 4, "X"))
        add_beveled_box(bm, at(0.0, 0.09, 0.12), (0.12, 0.05, 0.09), material_index=0,
                        bevel=0.012, rotation=rot @ Matrix.Rotation(0.5, 4, "X"))
        for sign in (-1, 1):
            add_sphere(bm, at(sign * 0.05, 0.15, -0.03), (0.033, 0.033, 0.028),
                       material_index=1, subdivisions=1)
        loose(4)
    elif variant % 3 == 1:
        # splayed ribcage half sunk into the stone
        for i in range(6):
            t = i / 5.0
            spread = 0.32 * (0.45 + 0.55 * math.sin(t * math.pi))
            add_poly_tube(bm, [
                at(-spread, 0.02, -0.16 + t * 0.32),
                at(-spread * 0.85, 0.13, -0.12 + t * 0.36),
                at(0, 0.17, -0.14 + t * 0.38),
                at(spread * 0.85, 0.13, -0.12 + t * 0.36),
                at(spread, 0.02, -0.16 + t * 0.32),
            ], 0.018, material_index=0, sides=5)
        add_bone(bm, at(0, 0.05, -0.30), at(0, 0.07, 0.10), 0.05, material_index=0)
        add_sphere(bm, at(rnd.uniform(-0.3, 0.3), 0.09, 0.30), (0.10, 0.09, 0.10),
                   material_index=0, subdivisions=1)
        loose(3)
    else:
        # a clean-ish skeleton: skull, spine, ribs, limbs
        add_sphere(bm, at(0, 0.10, 0.52), (0.10, 0.11, 0.10), material_index=0,
                   subdivisions=2)
        for i in range(7):
            add_sphere(bm, at(0, 0.05, -0.16 + i * 0.075), (0.028, 0.026, 0.034),
                       material_index=0, subdivisions=1)
        for i in range(6):
            t = i / 5.0
            add_poly_tube(bm, [
                at(-0.15 * (1 - t * 0.7), 0.04, -0.10 + t * 0.44),
                at(-0.09 * (1 - t * 0.7), 0.13, -0.06 + t * 0.46),
                at(0.09 * (1 - t * 0.7), 0.13, -0.06 + t * 0.46),
                at(0.15 * (1 - t * 0.7), 0.04, -0.10 + t * 0.44),
            ], 0.014, material_index=0, sides=5)
        for sign in (-1, 1):
            add_bone(bm, at(sign * 0.20, 0.04, 0.20), at(sign * 0.23, 0.04, -0.18),
                     0.026, material_index=0)
        loose(2, 0.4)

    return new_object(name, bm, [mats["bone"], mats["char"]])


# ----------------------------------------------------------------- placement --
def _remove(prefixes):
    """Delete previously generated props so a rebuild is idempotent.

    Note the marker empties (Prop_Barrel, Altar, Life_N, Hint_Lectern, ...) are
    NOT in this list - build_level creates them first and the props hang off
    them, so removing them here would orphan everything.
    """
    for ob in list(bpy.data.objects):
        if any(ob.name.startswith(p) for p in prefixes):
            me = ob.data
            bpy.data.objects.remove(ob, do_unlink=True)
            if me is not None and me.users == 0 and isinstance(me, bpy.types.Mesh):
                bpy.data.meshes.remove(me)


def torch_wall_facing(c, r):
    """Pick an adjacent wall for a sconce.

    Torch markers are floor-cell anchors. A wall bracket has to actually touch
    stone, so walk the four neighbours in a fixed order and take the first wall.
    Returns (world_xy, out-angle, on_wall); when the cell is open floor the
    caller switches to a standing torch instead.
    """
    import build_level as L

    for dc, dr, angle in ((0, -1, 0.0), (0, 1, math.pi),
                         (1, 0, -math.pi / 2), (-1, 0, math.pi / 2)):
        nc, nr = c + dc, r + dr
        if 0 <= nr < L.H and 0 <= nc < L.W and L.grid[nr][nc] == "#":
            cx, cy, cz = L.cell_center(c, r)
            half = L.CELL * 0.5
            return ((cx + dc * (half - 0.02), cz + dr * (half - 0.02)), angle, True)
    return ((0.0, 0.0), 0.0, False)


def scatter_cells(count, seed, taken):
    """Random floor cells that no prop already occupies."""
    import build_level as L

    rnd = random.Random(seed)
    cells = []
    for r in range(1, L.H - 1):
        for c in range(1, L.W - 1):
            if L.grid[r][c] != "." or (c, r) in taken:
                continue
            cells.append((c, r))
    rnd.shuffle(cells)
    out = []
    for (c, r) in cells:
        if any(abs(c - tc) <= 1 and abs(r - tr) <= 1 for tc, tr in out):
            continue  # keep them apart so you never get a pile-up
        out.append((c, r))
        if len(out) >= count:
            break
    return out


def main(remains_count=26, seed=4242):
    import build_level as L

    mats = ensure_materials()
    _remove(["Altar_Block", "AltarCrystal", "Brazier_", "Flame_", "Hint_Lectern_Mesh",
             "Hint_Lectern_Top", "Prop_Barrel_Mesh", "Prop_Barrel_4_Mesh",
             "Prop_Crate_Mesh", "Prop_Crate_2_Mesh", "Prop_Crate_5_Mesh",
             "PropTorch_", "PropFlame_", "Remains_"])

    taken = set()

    ac = L.find("Q")[0]
    taken.add(ac)
    base = L.cell_center(ac[0], ac[1])
    altar = bpy.data.objects.get("Altar")
    if altar:
        parent_to(build_altar("Altar_Block", mats, base, 0), altar)
        parent_to(build_altar_crystal("AltarCrystal", mats, base, L.CRYSTAL_HEIGHT), altar)

    lc = L.find("H")[0]
    taken.add(lc)
    lectern = bpy.data.objects.get("Hint_Lectern")
    if lectern:
        parent_to(build_lectern("Hint_Lectern_Mesh", mats, L.cell_center(lc[0], lc[1])),
                  lectern)

    for index, bc in enumerate(L.find("B"), start=1):
        taken.add(bc)
        life = bpy.data.objects.get(f"Life_{index}")
        if not life:
            continue
        pos = L.cell_center(bc[0], bc[1])
        parent_to(build_brazier(f"Brazier_{index}", mats, pos), life)
        parent_to(build_brazier_fire(f"Flame_{index}", mats, pos), life)

    for name, loc, kind in (("Prop_Barrel", (7.0, 0.0, 55.6), "barrel"),
                            ("Prop_Barrel_4", (15.0, 0.0, 5.6), "barrel"),
                            ("Prop_Crate", (27.4, 0.0, 13.0), "crate"),
                            ("Prop_Crate_2", (27.4, 0.0, 49.0), "crate"),
                            ("Prop_Crate_5", (54.0, 0.0, 9.5), "crate")):
        empty = bpy.data.objects.get(name)
        if not empty:
            continue
        bm = bmesh.new()
        if kind == "barrel":
            add_cylinder(bm, (loc[0], 0.55, loc[2]), 0.40, 0.45, 1.1, segments=12,
                         material_index=0, rotation=UP)
            for y in (0.28, 0.82):
                add_cylinder(bm, (loc[0], y, loc[2]), 0.46, 0.46, 0.07, segments=12,
                             material_index=1, rotation=UP, cap_ends=False)
        else:
            add_beveled_box(bm, (loc[0], 0.38, loc[2]), (0.75, 0.76, 0.75),
                            material_index=0, bevel=0.03)
            for dy in (-0.24, 0.24):
                add_box(bm, (loc[0], 0.38 + dy, loc[2]), (0.81, 0.10, 0.81),
                        material_index=1)
        parent_to(new_object(f"{name}_Mesh", bm, [mats["wood"], mats["iron_rust"]]), empty)

    # torch sconces, standing on their own where the cell has no wall
    sconces = 0
    stands = 0
    for (c, r) in L.torch_cells():
        (x, z), facing, on_wall = torch_wall_facing(c, r)
        if on_wall:
            loc = (x, L.TORCH_HEIGHT - 0.12, z)
            build_torch_sconce(f"PropTorch_{c}_{r}", mats, loc, facing)
            build_torch_flame(f"PropFlame_{c}_{r}", mats, loc, facing)
            sconces += 1
        else:
            cx, cy, cz = L.cell_center(c, r)
            loc = (cx, 0.0, cz)
            build_torch_stand(f"PropTorch_{c}_{r}", mats, loc)
            build_torch_stand_flame(f"PropFlame_{c}_{r}", mats, loc)
            stands += 1

    for i, (c, r) in enumerate(scatter_cells(remains_count, seed, taken)):
        bx, _, bz = L.cell_center(c, r, 0.0)
        pos = (bx + random.uniform(-0.5, 0.5), 0.0, bz + random.uniform(-0.5, 0.5))
        build_remains(f"Remains_{i}", mats, pos, seed=seed, variant=i)

    return {
        "sconces": sconces,
        "standing_torches": stands,
        "braziers": len(L.find("B")),
        "remains": remains_count,
        "prop_tris": sum(
            sum(max(len(p.vertices) - 2, 0) for p in ob.data.polygons)
            for ob in bpy.data.objects
            if ob.type == "MESH" and any(
                ob.name.startswith(p) for p in
                ("Altar_Block", "AltarCrystal", "Brazier_", "Flame_",
                 "Hint_Lectern_Mesh", "PropTorch_", "PropFlame_", "Remains_"))),
    }


# ------------------------------------------------------------------ preview --
def preview(sets, out_dir=None, azimuth=35, elevation=18, pad=1.3, res=(900, 700)):
    """Workbench stills of each prop, isolated and framed.

    Building the camera basis by hand matters: `to_track_quat` rolls the frame
    in a Y-up world, which silently shows every prop lying on its side.
    """
    out_dir = out_dir or os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                      "prop_preview")
    os.makedirs(out_dir, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x, scene.render.resolution_y = res
    sh = scene.display.shading
    sh.light, sh.color_type = "STUDIO", "MATERIAL"
    sh.show_cavity, sh.cavity_type, sh.show_shadows = True, "BOTH", True

    cam = bpy.data.objects.get("PreviewCam")
    scene.camera = cam
    cam.data.type = "ORTHO"

    def aim(center, radius, az, el):
        a, e = math.radians(az), math.radians(el)
        off = Vector((math.sin(a) * math.cos(e), math.sin(e), math.cos(a) * math.cos(e)))
        cam.location = center + off * (radius * 4 + 2)
        z_axis = off
        x_axis = Vector((0, 1, 0)).cross(z_axis)
        x_axis = x_axis.normalized() if x_axis.length > 1e-6 else Vector((1, 0, 0))
        y_axis = z_axis.cross(x_axis)
        cam.matrix_world = Matrix(((x_axis.x, y_axis.x, z_axis.x, cam.location.x),
                                  (x_axis.y, y_axis.y, z_axis.y, cam.location.y),
                                  (x_axis.z, y_axis.z, z_axis.z, cam.location.z),
                                  (0.0, 0.0, 0.0, 1.0)))

    made = []
    for names, filename in sets:
        obs = [bpy.data.objects[n] for n in names if bpy.data.objects.get(n)]
        if not obs:
            continue
        for ob in bpy.data.objects:
            if ob.type == "MESH":
                ob.hide_render = ob not in obs
        cs = [ob.matrix_world @ v.co for ob in obs for v in ob.data.vertices]
        lo = Vector((min(c.x for c in cs), min(c.y for c in cs), min(c.z for c in cs)))
        hi = Vector((max(c.x for c in cs), max(c.y for c in cs), max(c.z for c in cs)))
        center = (lo + hi) * 0.5
        radius = max((hi - lo).length * 0.5, 0.2)
        aim(center, radius, azimuth, elevation)
        cam.data.ortho_scale = radius * 2 * pad
        scene.render.filepath = os.path.join(out_dir, filename)
        bpy.ops.render.render(write_still=True)
        made.append(filename)

    for ob in bpy.data.objects:          # leave the scene renderable again
        if ob.type == "MESH":
            ob.hide_render = False
    return made

if __name__ == "__main__":
    import json
    print("PROP RESULT", json.dumps(main(), indent=1))