"""Rebuild the orc so it matches the reference art (Orcs/*.jpg).

Shared traits across the references: desaturated grey-green skin, bright
red/orange eyes deep under a heavy brow, pointed ears jutting sideways, a
protruding jaw with visible teeth and upward tusks, huge sloping shoulders,
and ragged dark leather/chain over the body.

The existing OrcRig and the OrcAttack action are kept - the new mesh is
authored around the rig's rest pose and weighted to the same bones, so the
animation still drives it.

Run headless:
    blender --background dungeon.blend --python build_orc.py
"""

import math
import os
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))

SKIN, BONE, EYE, METAL, LEATHER = 0, 1, 2, 3, 4
rng = random.Random(20261015)

# vertex-index ranges -> (bone name, weight); filled while building
weights: list[tuple[str, list[int]]] = []


def track(verts, bone, weight=1.0):
    idx = [v.index for v in verts]
    weights.append((bone, idx, weight))


def merge_range(bone, start, end, weight=1.0):
    weights.append((bone, list(range(start, end)), weight))


# --------------------------------------------------------------- primitives --
def tube(bm, p0, p1, r0, r1, seg=10, mat=SKIN, squash=1.0, roll=0.0):
    """Tapered cylinder between two points. squash flattens the cross-section."""
    p0, p1 = Vector(p0), Vector(p1)
    axis = p1 - p0
    length = axis.length
    if length < 1e-6:
        return []
    zdir = axis.normalized()
    up = Vector((0, 0, 1)) if abs(zdir.z) < 0.9 else Vector((1, 0, 0))
    xdir = zdir.cross(up).normalized()
    ydir = zdir.cross(xdir).normalized()

    def ring(center, radius):
        pts = []
        for i in range(seg):
            a = (i / seg) * math.tau + roll
            v = center + xdir * (math.cos(a) * radius) + ydir * (math.sin(a) * radius * squash)
            pts.append(bm.verts.new(v))
        return pts

    a = ring(p0, r0)
    b = ring(p1, r1)
    faces = []
    for i in range(seg):
        j = (i + 1) % seg
        f = bm.faces.new((a[i], a[j], b[j], b[i]))
        f.material_index = mat
        faces.append(f)
    f = bm.faces.new(a)
    f.material_index = mat
    f2 = bm.faces.new(b)
    f2.material_index = mat
    for v in a + b:
        v.tag = True
    return a + b


def blob(bm, center, radii, seg=12, rings=8, mat=SKIN, rot=None, jitter=0.0):
    """Ellipsoid, optionally squashed/rotated and roughened."""
    mat_rot = rot if rot is not None else Matrix.Identity(4)
    center = Vector(center)
    verts = []
    rows = []
    for r in range(rings + 1):
        phi = math.pi * (r / rings)
        row = []
        for s in range(seg):
            th = (s / seg) * math.tau
            x = math.sin(phi) * math.cos(th)
            y = math.cos(phi)
            z = math.sin(phi) * math.sin(th)
            j = 1.0 + rng.uniform(-jitter, jitter) if jitter else 1.0
            p = Vector((x * radii[0] * j, y * radii[1] * j, z * radii[2] * j))
            p = mat_rot @ p + center
            row.append(bm.verts.new(p))
        rows.append(row)
    for r in range(rings):
        for s in range(seg):
            s2 = (s + 1) % seg
            f = bm.faces.new((rows[r][s], rows[r][s2], rows[r + 1][s2], rows[r + 1][s]))
            f.material_index = mat
    for row in rows:
        verts.extend(row)
    return verts


def cone_between(bm, base, tip, r_base, r_tip=0.004, seg=7, mat=SKIN, squash=1.0, bend=0.0):
    """Cone from base to tip, optionally bent sideways for tusks/claws."""
    base, tip = Vector(base), Vector(tip)
    axis = tip - base
    length = axis.length
    zdir = axis.normalized()
    up = Vector((0, 0, 1)) if abs(zdir.z) < 0.9 else Vector((1, 0, 0))
    xdir = zdir.cross(up).normalized()
    ydir = zdir.cross(xdir).normalized()
    mid = base + axis * 0.5 + xdir * bend

    def ring(center, radius):
        out = []
        for i in range(seg):
            a = (i / seg) * math.tau
            out.append(bm.verts.new(center + xdir * (math.cos(a) * radius) + ydir * (math.sin(a) * radius * squash)))
        return out

    a = ring(base, r_base)
    b = ring(mid, (r_base + r_tip) * 0.5)
    c = ring(tip, r_tip)
    faces = []
    for lo, hi in ((a, b), (b, c)):
        for i in range(seg):
            j = (i + 1) % seg
            f = bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
            f.material_index = mat
            faces.append(f)
    f = bm.faces.new(a)
    f.material_index = mat
    f2 = bm.faces.new(c)
    f2.material_index = mat
    return a + b + c, faces


def plate(bm, center, size, rot=None, mat=LEATHER, ragged=0.0, seg=10):
    """Flat armour plate / ragged leather panel."""
    rot = rot if rot is not None else Matrix.Identity(4)
    center = Vector(center)
    sx, sy, sz = size
    rows = []
    for r in range(seg):
        t = r / seg
        rad = math.sin(math.pi * (0.12 + 0.88 * t))
        row = []
        for s in range(seg):
            th = (s / seg) * math.tau
            jag = 1.0
            if t > 0.55 and ragged:
                jag = 1.0 - ragged * rng.random()
            x = math.cos(th) * sx * rad * jag
            y = math.sin(th) * sy * rad * jag
            for zz in (-sz, sz):
                pass
            top = bm.verts.new(rot @ Vector((x, y, sz * 0.5 * rad * jag)) + center)
            bot = bm.verts.new(rot @ Vector((x, y, -sz * 0.5 * rad * jag)) + center)
            row.append((top, bot))
        rows.append(row)
    verts = []
    for r in range(seg - 1):
        for s in range(seg):
            s2 = (s + 1) % seg
            t0, b0 = rows[r][s]
            t1, b1 = rows[r][s2]
            t0b, b0b = rows[r + 1][s]
            t1b, b1b = rows[r + 1][s2]
            f1 = bm.faces.new((t0, t1, t1b, t0b))
            f1.material_index = mat
            f2 = bm.faces.new((b0b, b1b, b1, b0))
            f2.material_index = mat
            verts.extend([t0, t1, t1b, t0b, b0b, b1b, b1, b0])
    for row in rows:
        for t, b in row:
            verts.extend([t, b])
    return verts


def box(bm, center, size, mat=SKIN, rot=None):
    center = Vector(center)
    rot = rot if rot is not None else Matrix.Identity(4)
    hx, hy, hz = (s * 0.5 for s in size)
    corners = [
        (-hx, -hy, -hz), (hx, -hy, -hz), (hx, hy, -hz), (-hx, hy, -hz),
        (-hx, -hy, hz), (hx, -hy, hz), (hx, hy, hz), (-hx, hy, hz),
    ]
    vs = [bm.verts.new(rot @ Vector(c) + center) for c in corners]
    quads = [(0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    for q in quads:
        f = bm.faces.new([vs[i] for i in q])
        f.material_index = mat
    return vs


def rot_x(deg):
    return Matrix.Rotation(math.radians(deg), 4, "X")


def rot_y(deg):
    return Matrix.Rotation(math.radians(deg), 4, "Y")


def rot_z(deg):
    return Matrix.Rotation(math.radians(deg), 4, "Z")


# --------------------------------------------------------------- materials ---
def principled(name, base, rough=0.6, metallic=0.0, emission=None, strength=0.0):
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
    if emission:
        e = bsdf.inputs.get("Emission Color") or bsdf.inputs.get("Emission")
        e.default_value = (*emission, 1.0)
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = strength
    return mat


def build_materials():
    return [
        principled("orc_skin", (0.205, 0.245, 0.170), rough=0.74),        # grey-green
        principled("bone", (0.50, 0.455, 0.325), rough=0.55),               # tusks / teeth / claws
        principled("emissive_crystal", (0.55, 0.06, 0.02), rough=0.25,  # red eyes
                   emission=(1.0, 0.13, 0.03), strength=7.0),
        principled("metal", (0.055, 0.058, 0.065), rough=0.5, metallic=1.0),
        principled("orc_leather", (0.072, 0.045, 0.028), rough=0.86),   # ragged armour
    ]


# ------------------------------------------------------------------- build ---
def build_geometry():
    bm = bmesh.new()

    # ---- legs ------------------------------------------------------------
    for side, sgn in (("L", -1), ("R", 1)):
        start = len(bm.verts)
        tube(bm, (sgn * 0.19, 1.02, 0.01), (sgn * 0.215, 0.58, 0.01), 0.205, 0.155, seg=10, squash=0.92)
        merge_range(f"thigh.{side}", start, len(bm.verts))

        start = len(bm.verts)
        tube(bm, (sgn * 0.215, 0.60, 0.01), (sgn * 0.225, 0.16, 0.02), 0.165, 0.105, seg=10, squash=0.92)
        blob(bm, (sgn * 0.215, 0.58, -0.03), (0.15, 0.13, 0.14), seg=10, rings=6)
        merge_range(f"shin.{side}", start, len(bm.verts))

        # boot + claws
        start = len(bm.verts)
        box(bm, (sgn * 0.225, 0.055, -0.07), (0.21, 0.11, 0.36), mat=LEATHER)
        merge_range(f"foot.{side}", start, len(bm.verts))
        start = len(bm.verts)
        for k in range(3):
            cone_between(bm, (sgn * 0.225 + (k - 1) * 0.06, 0.055, -0.24),
                         (sgn * 0.225 + (k - 1) * 0.065, 0.045, -0.33), 0.028, 0.006, seg=6, mat=BONE)
        merge_range(f"foot.{side}", start, len(bm.verts), 1.0)

    # ---- hips + loincloth -------------------------------------------------
    start = len(bm.verts)
    tube(bm, (0, 1.30, 0.0), (0, 0.99, 0.0), 0.30, 0.27, seg=12, squash=0.78)
    merge_range("hips", start, len(bm.verts))
    start = len(bm.verts)
    tube(bm, (0, 1.06, 0.0), (0, 0.74, -0.02), 0.315, 0.40, seg=14, squash=0.8, mat=LEATHER)
    merge_range("hips", start, len(bm.verts))

    # ---- torso ------------------------------------------------------------
    start = len(bm.verts)
    tube(bm, (0, 1.30, 0.0), (0, 1.64, 0.0), 0.295, 0.335, seg=14, squash=0.78)
    merge_range("spine", start, len(bm.verts))
    start = len(bm.verts)
    tube(bm, (0, 1.62, -0.01), (0, 1.90, -0.01), 0.355, 0.375, seg=14, squash=0.80)
    blob(bm, (0, 1.43, -0.12), (0.29, 0.21, 0.24), seg=12, rings=7)   # belly
    for sgn in (-1, 1):
        blob(bm, (sgn * 0.155, 1.79, -0.235), (0.17, 0.135, 0.115), seg=10, rings=6)  # pecs
        blob(bm, (sgn * 0.185, 1.875, 0.02), (0.165, 0.125, 0.155), seg=10, rings=6)   # traps
        blob(bm, (sgn * 0.235, 1.70, 0.17), (0.155, 0.235, 0.125), seg=10, rings=6)    # lats
    merge_range("chest", start, len(bm.verts))

    # chest harness (leather straps + a bone plate + rivets)
    start = len(bm.verts)
    for sgn in (-1, 1):
        box(bm, (sgn * 0.175, 1.70, -0.10), (0.11, 0.56, 0.40), mat=LEATHER, rot=rot_y(-sgn * 7))
    merge_range("chest", start, len(bm.verts))
    start = len(bm.verts)
    box(bm, (0, 1.71, -0.30), (0.26, 0.15, 0.06), mat=BONE, rot=rot_x(-18))
    for sgn in (-1, 1):
        blob(bm, (sgn * 0.085, 1.685, -0.305), (0.016, 0.016, 0.016), seg=6, rings=4, mat=METAL)
    merge_range("chest", start, len(bm.verts))

    # ---- shoulders / arms --------------------------------------------------
    for side, sgn in (("L", -1), ("R", 1)):
        start = len(bm.verts)
        tube(bm, (sgn * 0.06, 1.87, 0.02), (sgn * 0.33, 1.90, 0.01), 0.115, 0.145, seg=9, squash=0.9)
        merge_range(f"clavicle.{side}", start, len(bm.verts))

        start = len(bm.verts)
        blob(bm, (sgn * 0.46, 1.87, 0.0), (0.205, 0.20, 0.205), seg=12, rings=7)   # deltoid
        merge_range(f"shoulder.{side}", start, len(bm.verts))

        start = len(bm.verts)
        plate(bm, (sgn * 0.47, 1.90, 0.0), (0.27, 0.26, 0.16), mat=LEATHER, ragged=0.55,
              rot=rot_y(sgn * 12))
        merge_range(f"shoulder.{side}", start, len(bm.verts))

        start = len(bm.verts)
        tube(bm, (sgn * 0.50, 1.90, 0.0), (sgn * 0.585, 1.56, -0.01), 0.165, 0.135, seg=9, squash=0.92)
        merge_range(f"upperarm.{side}", start, len(bm.verts))

        start = len(bm.verts)
        blob(bm, (sgn * 0.585, 1.55, -0.01), (0.135, 0.13, 0.13), seg=9, rings=6)
        tube(bm, (sgn * 0.585, 1.56, -0.01), (sgn * 0.615, 1.22, -0.02), 0.145, 0.115, seg=9, squash=0.92)
        merge_range(f"forearm.{side}", start, len(bm.verts))

        start = len(bm.verts)
        tube(bm, (sgn * 0.60, 1.40, -0.015), (sgn * 0.615, 1.26, -0.02), 0.155, 0.135, seg=10, mat=LEATHER)
        merge_range(f"forearm.{side}", start, len(bm.verts))

        # fist + knuckles + thumb
        start = len(bm.verts)
        blob(bm, (sgn * 0.615, 1.11, -0.035), (0.125, 0.135, 0.115), seg=10, rings=6)
        for k in range(3):
            blob(bm, (sgn * 0.615 + (k - 1) * 0.045, 1.01, -0.075), (0.032, 0.032, 0.03), seg=7, rings=5)
        blob(bm, (sgn * 0.52, 1.09, -0.05), (0.045, 0.06, 0.045), seg=7, rings=5)
        for k in range(3):
            cone_between(bm, (sgn * 0.615 + (k - 1) * 0.045, 0.985, -0.07),
                         (sgn * 0.615 + (k - 1) * 0.05, 0.95, -0.10), 0.022, 0.005, seg=5, mat=BONE)
        merge_range(f"hand.{side}", start, len(bm.verts))

    # ---- neck --------------------------------------------------------------
    start = len(bm.verts)
    tube(bm, (0, 1.86, 0.0), (0, 2.09, -0.01), 0.185, 0.165, seg=12, squash=0.9)
    merge_range("neck", start, len(bm.verts))

    # ---- head: skull, brow, eyes, ears, nose --------------------------------
    start = len(bm.verts)
    blob(bm, (0, 2.195, -0.02), (0.225, 0.245, 0.255), seg=14, rings=9, jitter=0.035)
    # muzzle - heavy, protruding lower face
    tube(bm, (0, 2.125, -0.11), (0, 2.035, -0.30), 0.195, 0.115, seg=12, squash=0.9)
    blob(bm, (0, 2.015, -0.30), (0.125, 0.08, 0.08), seg=10, rings=6)   # snout tip
    # heavy brow ridge, jutting forward over the eyes
    box(bm, (0, 2.20, -0.165), (0.405, 0.105, 0.14), mat=SKIN, rot=rot_x(26))
    for sgn in (-1, 1):
        blob(bm, (sgn * 0.175, 2.175, -0.11), (0.085, 0.08, 0.10), seg=9, rings=6)  # temple/cheekbone
        blob(bm, (sgn * 0.125, 2.085, -0.17), (0.075, 0.07, 0.09), seg=9, rings=6)  # jaw muscle
    # nose
    box(bm, (0, 2.075, -0.285), (0.095, 0.085, 0.07), mat=SKIN, rot=rot_x(-18))
    for sgn in (-1, 1):
        blob(bm, (sgn * 0.05, 2.04, -0.305), (0.03, 0.028, 0.032), seg=7, rings=5)
    merge_range("head", start, len(bm.verts))

    # deep eye sockets + glowing red eyes (eyes must clear the skull surface)
    start = len(bm.verts)
    for sgn in (-1, 1):
        blob(bm, (sgn * 0.115, 2.145, -0.20), (0.085, 0.075, 0.08), seg=9, rings=6, mat=SKIN)
    merge_range("head", start, len(bm.verts))
    start = len(bm.verts)
    for sgn in (-1, 1):
        blob(bm, (sgn * 0.115, 2.142, -0.245), (0.05, 0.044, 0.045), seg=9, rings=6, mat=EYE)
    merge_range("head", start, len(bm.verts))

    # pointed ears, swept back and up
    start = len(bm.verts)
    for sgn in (-1, 1):
        cone_between(bm, (sgn * 0.205, 2.235, 0.01), (sgn * 0.415, 2.315, 0.135),
                     0.095, 0.014, seg=8, mat=SKIN, squash=0.5, bend=-sgn * 0.03)
        cone_between(bm, (sgn * 0.20, 2.185, -0.01), (sgn * 0.365, 2.175, 0.10),
                     0.07, 0.011, seg=7, mat=SKIN, squash=0.46, bend=-sgn * 0.02)
    merge_range("head", start, len(bm.verts))

    # grimy dark crest / matted hair on the back of the skull
    start = len(bm.verts)
    blob(bm, (0, 2.21, 0.135), (0.185, 0.175, 0.135), seg=11, rings=7, mat=LEATHER, jitter=0.12)
    for k in range(5):
        ang = -0.7 + k * 0.35
        cone_between(bm,
                     (math.sin(ang) * 0.13, 2.30, 0.13 + math.cos(ang) * 0.03),
                     (math.sin(ang) * 0.20, 2.40 + rng.uniform(-0.03, 0.03), 0.15 + math.cos(ang) * 0.05),
                     0.045, 0.008, seg=6, mat=LEATHER, squash=0.55)
    merge_range("head", start, len(bm.verts))

    # ---- upper teeth + tusks ------------------------------------------------
    start = len(bm.verts)
    for sgn in (-1, 1):
        for k in (0, 1, 2):
            x = sgn * (0.06 + k * 0.05)
            cone_between(bm, (x, 2.055, -0.285), (x, 1.955, -0.27), 0.03, 0.008, seg=6, mat=BONE)
    # big upward tusks, curving outward like the references
    for sgn in (-1, 1):
        cone_between(bm, (sgn * 0.115, 2.045, -0.285), (sgn * 0.155, 2.265, -0.215),
                     0.072, 0.014, seg=8, mat=BONE, bend=sgn * 0.025)
    merge_range("head", start, len(bm.verts))

    # ---- lower jaw (weighted to the jaw bone so the clip animates it) -------
    start = len(bm.verts)
    tube(bm, (0, 2.05, -0.08), (0, 1.995, -0.27), 0.175, 0.115, seg=11, squash=0.88)
    blob(bm, (0, 1.985, -0.28), (0.12, 0.07, 0.065), seg=9, rings=6)
    for sgn in (-1, 1):  # jaw corner spikes
        cone_between(bm, (sgn * 0.125, 2.0, -0.20), (sgn * 0.195, 2.05, -0.13), 0.036, 0.008, seg=6, mat=BONE)
    merge_range("jaw", start, len(bm.verts))
    start = len(bm.verts)
    for sgn in (-1, 1):
        for k in (0, 1):
            x = sgn * (0.055 + k * 0.055)
            cone_between(bm, (x, 2.01, -0.27), (x, 2.065, -0.26), 0.026, 0.007, seg=6, mat=BONE)
        cone_between(bm, (sgn * 0.04, 2.015, -0.275), (sgn * 0.055, 1.95, -0.27), 0.026, 0.007, seg=6, mat=BONE)
    merge_range("jaw", start, len(bm.verts))

    bm.normal_update()
    bm.to_mesh_preserve_all_data_layers(bm, target=None) if False else None
    return bm


def finish(bm, obj):
    old = obj.data
    obj.data = None
    if old.users == 0:
        bpy.data.meshes.remove(old)
    me = bpy.data.meshes.new("Orc_Hide")
    bm.to_mesh(me)
    bm.free()
    me.name = "Orc_Hide"
    for m in build_materials():
        me.materials.append(m)
    obj.data = me

    # vertex groups
    me.update()
    for bone, idx, weight in weights:
        vg = obj.vertex_groups.get(bone)
        if vg is None:
            vg = obj.vertex_groups.new(name=bone)
        valid = [i for i in idx if i < len(me.vertices)]
        if valid:
            vg.add(valid, weight, "REPLACE")

    for mod in list(obj.modifiers):
        if mod.type == "ARMATURE":
            obj.modifiers.remove(mod)
    mod = obj.modifiers.new("Armature", "ARMATURE")
    mod.object = bpy.data.objects["OrcRig"]

    # grimy vertex colours: dirtier low down, on the skin slot only
    col = me.color_attributes.get("Col") or me.color_attributes.new(name="Col", type="FLOAT_COLOR", domain="CORNER")
    skin_polys = {p.index for p in me.polygons if p.material_index == SKIN}
    for p in me.polygons:
        if p.index not in skin_polys:
            continue
        for li in p.loop_indices:
            vi = me.loops[li].vertex_index
            co = me.vertices[vi].co
            dirt = max(0.0, min(1.0, (1.55 - co.y) / 1.1))
            n = 0.82 + 0.18 * math.sin(co.x * 9.1 + co.z * 7.3)
            v = 1.0 - 0.34 * dirt * n
            col.data[li].color = (v, v * 0.985, v * 0.94, 1.0)
    return me


def aim(obj, loc, target, up=(0, 1, 0)):
    """Aim an object at `target`. World up is +Y here (the dungeon is Y-up)."""
    loc = Vector(loc)
    target = Vector(target)
    zaxis = (loc - target).normalized()          # object -Z looks at the target
    xaxis = Vector(up).cross(zaxis).normalized()
    yaxis = zaxis.cross(xaxis)
    obj.location = loc
    obj.rotation_euler = Matrix((xaxis, yaxis, zaxis)).transposed().to_euler()


def preview(path, loc=(0.0, 1.15, -3.6), target=(0.0, 1.25, 0.0), res=(520, 820)):
    scene = bpy.context.scene
    cam = bpy.data.objects.get("PreviewCam")
    if cam is None:
        cam = bpy.data.objects.new("PreviewCam", bpy.data.cameras.new("PreviewCam"))
        scene.collection.objects.link(cam)
    cam.data.lens = 50
    aim(cam, loc, target)
    scene.camera = cam

    # three-point rig (created here so headless runs are self-contained)
    for name, offset, energy, color, size in (
        ("PreviewKey", (-2.4, 2.0, -2.8), 260, (1.0, 0.95, 0.88), 3.0),
        ("PreviewRim", (2.6, 1.8, 2.0), 150, (0.5, 0.65, 1.0), 2.0),
        ("PreviewFill", (1.6, 0.6, -3.0), 70, (0.85, 0.82, 1.0), 3.0),
    ):
        light = bpy.data.objects.get(name)
        if light is None or light.type != "LIGHT":
            data = bpy.data.lights.get(name) or bpy.data.lights.new(name, "AREA")
            if light:
                bpy.data.objects.remove(light, do_unlink=True)
            light = bpy.data.objects.new(name, data)
            scene.collection.objects.link(light)
        light.data.energy = energy
        light.data.size = size
        light.data.color = color
        aim(light, Vector(target) + Vector(offset), target)
        light.hide_render = False
        light.hide_viewport = False

    hidden = []
    for ob in scene.objects:
        if ob.type == "MESH" and ob.name != "Orc_Hide":
            hidden.append(ob)
            ob.hide_render = True
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x, scene.render.resolution_y = res
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.view_settings.view_transform = "Standard"
    try:
        scene.eevee.taa_render_samples = 16
    except Exception:
        pass
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    for ob in hidden:
        ob.hide_render = False


def export_orc(path=None):
    """Export the Orc collection (rig + body + six weapons) as GLB."""
    path = path or os.path.join(HERE, "orc.glb")
    coll = bpy.data.collections.get("Orc")
    if coll is None:
        raise RuntimeError("Orc collection missing")

    bpy.ops.object.select_all(action="DESELECT")
    for ob in coll.objects:
        ob.select_set(True)
    bpy.context.view_layer.objects.active = bpy.data.objects["OrcRig"]

    kwargs = dict(filepath=path, export_format="GLB", export_yup=True, export_apply=True,
                  use_selection=True, export_cameras=False, export_lights=False)
    try:
        bpy.ops.export_scene.gltf(**kwargs, export_image_format="WEBP")
    except TypeError:
        bpy.ops.export_scene.gltf(**kwargs)

    with open(path, "rb") as f:
        data = f.read()
    import json as _json
    import struct as _struct
    ln = _struct.unpack_from("<I", data, 12)[0]
    js = _json.loads(data[20:20 + ln].decode("utf-8"))
    return {
        "path": path,
        "bytes": len(data),
        "nodes": len(js.get("nodes", [])),
        "meshes": [m.get("name") for m in js.get("meshes", [])],
        "materials": [m.get("name") for m in js.get("materials", [])],
        "animations": [a.get("name") for a in js.get("animations", [])],
        "skins": len(js.get("skins", [])),
    }


def main():
    obj = bpy.data.objects["Orc_Hide"]
    weights.clear()
    bm = build_geometry()
    me = finish(bm, obj)
    info = export_orc()
    preview(os.path.join(HERE, "orc_preview_front.png"), loc=(0.0, 1.20, -3.4), target=(0.0, 1.35, 0.0))
    preview(os.path.join(HERE, "orc_preview_side.png"), loc=(-3.4, 1.20, 0.0), target=(0.0, 1.35, 0.0))
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "dungeon.blend"))
    print("ORC RESULT", {
        "verts": len(me.vertices),
        "polys": len(me.polygons),
        "groups": sorted({b for b, _, _ in weights}),
        "export": info,
    })


if __name__ == "__main__":
    main()