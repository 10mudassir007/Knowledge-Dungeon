# Rebuild dungeon walls: continuous plinth / recessed field / cornice shell
# + medieval ashlar concrete material, baked to textures for the GLB export.
# Run with: exec(open(...).read()) inside Blender.
import bpy, bmesh, os, json, struct
import numpy as np
from mathutils import Vector

ROOT = r"D:\Portfolio\Knowledge-Dungeon\dungeon"
TEX = os.path.join(ROOT, "textures")
os.makedirs(TEX, exist_ok=True)

PLINTH_TOP = 0.45
CORNICE_BOT = 2.55
INSET = 0.10
HEIGHT = 3.0
TILE = 4.0  # metres per baked texture tile

grid = [l for l in open(os.path.join(ROOT, "map.txt")).read().splitlines() if l.strip()]
H = len(grid)
W = max(len(l) for l in grid)

def at(c, r):
    if 0 <= c < W and 0 <= r < H:
        return grid[r][c]
    return '#'

def is_floor(c, r):
    return at(c, r) != '#'

# ---------------------------------------------------------------- geometry ---
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
    x0, x1, z0, z1 = c, c + 1, r, r + 1
    for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        if not is_floor(c + dc, r + dr):
            continue
        # bottom band: plinth, full plane
        if dc == 1:
            quad_x(1, x1, 0.0, PLINTH_TOP, z0, z1)
            quad_x(1, x1 - INSET, PLINTH_TOP, CORNICE_BOT, z0, z1)
            quad_x(1, x1, CORNICE_BOT, HEIGHT, z0, z1)
        elif dc == -1:
            quad_x(-1, x0, 0.0, PLINTH_TOP, z0, z1)
            quad_x(-1, x0 + INSET, PLINTH_TOP, CORNICE_BOT, z0, z1)
            quad_x(-1, x0, CORNICE_BOT, HEIGHT, z0, z1)
        elif dr == 1:
            quad_z(1, z1, 0.0, PLINTH_TOP, x0, x1)
            quad_z(1, z1 - INSET, PLINTH_TOP, CORNICE_BOT, x0, x1)
            quad_z(1, z1, CORNICE_BOT, HEIGHT, x0, x1)
        else:
            quad_z(-1, z0, 0.0, PLINTH_TOP, x0, x1)
            quad_z(-1, z0 + INSET, PLINTH_TOP, CORNICE_BOT, x0, x1)
            quad_z(-1, z0, CORNICE_BOT, HEIGHT, x0, x1)
    # plinth ledge (visible round the recess) and cornice soffit
    quad_y(1, PLINTH_TOP, x0, x1, z0, z1)
    quad_y(-1, CORNICE_BOT, x0, x1, z0, z1)

bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
bm.normal_update()

# box-projected UVs: 1 UV unit == TILE metres, world-anchored
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

walls_me = bpy.data.meshes.new("Walls")
bm.to_mesh(walls_me)
bm.free()

old_walls = bpy.data.objects.get("Walls")
old_colls = list(old_walls.users_collection) if old_walls else []
old_mat = None
if old_walls and old_walls.data.materials:
    old_mat = old_walls.data.materials[0]

other_users = [o.name for o in bpy.data.objects
               if o.type == 'MESH' and o.name != "Walls" and old_mat
               and old_mat.name in [m.name for m in o.data.materials if m]]

if old_mat is not None and other_users:
    old_mat.name = "stone_wall_props"
    mat = bpy.data.materials.new("stone_wall")
else:
    mat = old_mat if old_mat is not None else bpy.data.materials.new("stone_wall")
    mat.name = "stone_wall"

if old_walls:
    bpy.data.objects.remove(old_walls, do_unlink=True)

walls = bpy.data.objects.new("Walls", walls_me)
walls_me.materials.append(mat)
target_coll = old_colls[0] if old_colls else bpy.context.scene.collection
target_coll.objects.link(walls)
for m in [m for m in bpy.data.meshes if m.users == 0]:
    bpy.data.meshes.remove(m)
walls_me.name = "Walls"

# ------------------------------------------------------------- material -----
nt = mat.node_tree
nt.nodes.clear()
for im in [i for i in bpy.data.images if i.name.startswith("wall_")]:
    bpy.data.images.remove(im)
N = nt.nodes

def node(t, **kw):
    n = N.new(t)
    for k, v in kw.items():
        setattr(n, k, v)
    return n

def link(a, b, ia=None, ib=None):
    s = a.outputs[ia] if isinstance(ia, int) else a.outputs[ia]
    d = b.inputs[ib] if isinstance(ib, int) else b.inputs[ib]
    nt.links.new(s, d)

uvn = node('ShaderNodeUVMap', uv_map="UVMap")
sep = node('ShaderNodeSeparateXYZ')
link(uvn, sep, 'UV', 'Vector')
U = sep.outputs['X']
V = sep.outputs['Y']

def math2(op, a, b=None, c=None):
    n = node('ShaderNodeMath', operation=op)
    if isinstance(a, (int, float)):
        n.inputs[0].default_value = a
    else:
        nt.links.new(a, n.inputs[0])
    if b is not None:
        if isinstance(b, (int, float)):
            n.inputs[1].default_value = b
        else:
            nt.links.new(b, n.inputs[1])
    if c is not None:
        if isinstance(c, (int, float)):
            n.inputs[2].default_value = c
        else:
            nt.links.new(c, n.inputs[2])
    return n.outputs[0]

TAU = 6.2831853

def periodic_noise(fx, fy, scale, detail, ww=0.0):
    """4D noise sampled on two circles -> seamless over the whole tile."""
    cu = math2('COSINE', math2('MULTIPLY', math2('MULTIPLY', U, float(fx)), TAU))
    su = math2('SINE', math2('MULTIPLY', math2('MULTIPLY', U, float(fx)), TAU))
    cv = math2('COSINE', math2('MULTIPLY', math2('MULTIPLY', V, float(fy)), TAU))
    sv = math2('SINE', math2('MULTIPLY', math2('MULTIPLY', V, float(fy)), TAU))
    comb = node('ShaderNodeCombineXYZ')
    nt.links.new(cu, comb.inputs[0])
    nt.links.new(su, comb.inputs[1])
    nt.links.new(cv, comb.inputs[2])
    n = node('ShaderNodeTexNoise')
    n.noise_dimensions = '4D'
    n.inputs['Scale'].default_value = scale
    n.inputs['Detail'].default_value = detail
    n.inputs['Roughness'].default_value = 0.55
    nt.links.new(comb.outputs['Vector'], n.inputs['Vector'])
    nt.links.new(sv, n.inputs['W'])
    return n.outputs['Fac']

# ashlar grid: 1.0 m x 0.4 m bricks in a 4 m tile -> 0.25 x 0.1 in UV
BW, RH = 0.25, 0.10
brick = node('ShaderNodeTexBrick')
brick.inputs['Scale'].default_value = 1.0
brick.inputs['Mortar Size'].default_value = 0.005
brick.inputs['Mortar Smooth'].default_value = 0.003
brick.inputs['Brick Width'].default_value = BW
brick.inputs['Row Height'].default_value = RH
brick.offset = 0.5
nt.links.new(uvn.outputs['UV'], brick.inputs['Vector'])
# Fac = 1 on mortar, 0 on brick faces -> invert into a brick mask
mask = math2('SUBTRACT', 1.0, brick.outputs['Fac'])

rowR = math2('FLOOR', math2('MULTIPLY', V, 1.0 / RH))
rowMod2 = math2('MODULO', rowR, 2.0)
shift = math2('MULTIPLY', rowMod2, BW * 0.5)
bx = math2('FLOOR', math2('DIVIDE', math2('SUBTRACT', U, shift), BW))
bx4 = math2('MODULO', bx, 4.0)
row10 = math2('MODULO', rowR, 10.0)

def white(x, y, w):
    comb = node('ShaderNodeCombineXYZ')
    nt.links.new(x, comb.inputs[0])
    nt.links.new(y, comb.inputs[1])
    comb.inputs[2].default_value = w
    wn = node('ShaderNodeTexWhiteNoise')
    wn.noise_dimensions = '3D'
    nt.links.new(comb.outputs['Vector'], wn.inputs['Vector'])
    return wn.outputs['Value']

v1 = white(bx4, row10, 3.7)
v2 = white(bx4, row10, 9.1)

def rgba_mix(fac, a, b, blend='MIX'):
    m = node('ShaderNodeMix')
    m.data_type = 'RGBA'
    m.blend_type = blend
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

def float_mix(fac, a, b):
    m = node('ShaderNodeMix')
    m.data_type = 'FLOAT'
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

def map_range(val, fmn, fmx, tmn, tmx):
    n = node('ShaderNodeMapRange')
    if isinstance(val, (int, float)):
        n.inputs['Value'].default_value = val
    else:
        nt.links.new(val, n.inputs['Value'])
    n.inputs['From Min'].default_value = fmn
    n.inputs['From Max'].default_value = fmx
    n.inputs['To Min'].default_value = tmn
    n.inputs['To Max'].default_value = tmx
    return n.outputs['Result']

# ---- base colour
stain = map_range(periodic_noise(1, 1, 2.6, 6), 0.32, 0.68, 0.70, 1.06)
streak = map_range(periodic_noise(4, 1, 2.4, 4), 0.35, 0.65, 0.82, 1.02)
brick_l = rgba_mix(v2, (0.335, 0.315, 0.278), (0.545, 0.520, 0.470))
brick_l = rgba_mix(1.0, brick_l, stain, 'MULTIPLY')
brick_l = rgba_mix(1.0, brick_l, streak, 'MULTIPLY')
scalar = map_range(v1, 0.25, 0.8, 0.82, 1.16)
tint = node('ShaderNodeCombineColor')
for i in range(3):
    nt.links.new(scalar, tint.inputs[i])
brick_c = rgba_mix(1.0, brick_l, tint.outputs['Color'], 'MULTIPLY')
mortar_c = rgba_mix(periodic_noise(3, 3, 5.0, 3), (0.065, 0.060, 0.055), (0.115, 0.105, 0.095))
base_col = rgba_mix(mask, mortar_c, brick_c)

# ---- roughness
grit = periodic_noise(12, 12, 9.0, 4)
r_brick = map_range(grit, 0.2, 0.8, 0.42, 0.72)
rough = float_mix(mask, 0.94, r_brick)

# ---- bump stack
bump_a = node('ShaderNodeBump')
bump_a.inputs['Strength'].default_value = 0.55
bump_a.inputs['Distance'].default_value = 0.02
nt.links.new(mask, bump_a.inputs['Height'])
bump_b = node('ShaderNodeBump')
bump_b.inputs['Strength'].default_value = 0.18
bump_b.inputs['Distance'].default_value = 0.004
nt.links.new(grit, bump_b.inputs['Height'])
nt.links.new(bump_a.outputs['Normal'], bump_b.inputs['Normal'])

bsdf = node('ShaderNodeBsdfPrincipled')
nt.links.new(base_col, bsdf.inputs['Base Color'])
nt.links.new(rough, bsdf.inputs['Roughness'])
nt.links.new(bump_b.outputs['Normal'], bsdf.inputs['Normal'])
out = node('ShaderNodeOutputMaterial')
nt.links.new(bsdf.outputs['BSDF'], out.inputs['Surface'])

# ------------------------------------------------------------------ bake ----
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 2
scene.cycles.use_denoising = False
scene.render.bake.margin = 8

for o in bpy.context.view_layer.objects:
    o.select_set(False)
walls.select_set(True)
bpy.context.view_layer.objects.active = walls

def bake_pass(img, bake_type):
    n = node('ShaderNodeTexImage')
    n.image = img
    for nn in N:
        nn.select = False
    n.select = True
    N.active = n
    bpy.ops.object.bake(type=bake_type, pass_filter={'COLOR'} if bake_type == 'DIFFUSE' else set())
    N.remove(n)

base_img = bpy.data.images.new("wall_basecolor", 2048, 2048, alpha=False)
base_img.colorspace_settings.name = 'sRGB'
bake_pass(base_img, 'DIFFUSE')
base_img.filepath_raw = os.path.join(TEX, "wall_basecolor.png")
base_img.file_format = 'PNG'
base_img.save()

norm_img = bpy.data.images.new("wall_normal", 2048, 2048, alpha=False)
norm_img.colorspace_settings.name = 'Non-Color'
bake_pass(norm_img, 'NORMAL')
norm_img.filepath_raw = os.path.join(TEX, "wall_normal.png")
norm_img.file_format = 'PNG'
norm_img.save()

rough_img = bpy.data.images.new("wall_rough", 1024, 1024, alpha=False)
rough_img.colorspace_settings.name = 'Non-Color'
bake_pass(rough_img, 'ROUGHNESS')
rough_img.filepath_raw = os.path.join(TEX, "wall_rough.png")
rough_img.file_format = 'PNG'
rough_img.save()

# ---- pack ORM (R unused=1, G roughness, B metallic=0)
rp = np.empty(1024 * 1024 * 4, dtype=np.float32)
rough_img.pixels.foreach_get(rp)
orm = np.ones(1024 * 1024 * 4, dtype=np.float32)
orm[1::4] = rp[1::4]
orm[2::4] = 0.0
orm_img = bpy.data.images.new("wall_orm", 1024, 1024, alpha=False)
orm_img.colorspace_settings.name = 'Non-Color'
orm_img.pixels.foreach_set(orm)
orm_img.filepath_raw = os.path.join(TEX, "wall_orm.png")
orm_img.file_format = 'PNG'
orm_img.save()

for im in (base_img, norm_img, orm_img):
    im.pack()

# ------------------------------------------------- reassign: baked material -
nt.nodes.clear()

def img_node(img):
    n = N.new('ShaderNodeTexImage')
    n.image = img
    return n

bsdf = N.new('ShaderNodeBsdfPrincipled')
bsdf.inputs['Metallic'].default_value = 0.0
out2 = N.new('ShaderNodeOutputMaterial')
bc = img_node(base_img)
nt.links.new(bc.outputs['Color'], bsdf.inputs['Base Color'])
nm = img_node(norm_img)
nm_map = N.new('ShaderNodeNormalMap')
nt.links.new(nm.outputs['Color'], nm_map.inputs['Color'])
nt.links.new(nm_map.outputs['Normal'], bsdf.inputs['Normal'])
orm_n = img_node(orm_img)
orm_sep = N.new('ShaderNodeSeparateColor')
nt.links.new(orm_n.outputs['Color'], orm_sep.inputs['Color'])
nt.links.new(orm_sep.outputs['Green'], bsdf.inputs['Roughness'])
nt.links.new(orm_sep.outputs['Blue'], bsdf.inputs['Metallic'])
nt.links.new(bsdf.outputs['BSDF'], out2.inputs['Surface'])
N.active = bc

# ----------------------------------------------------------------- output ---
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "dungeon.blend"))

glb = os.path.join(ROOT, "dungeon.glb")
kwargs = dict(filepath=glb, export_format='GLB', export_yup=True, export_apply=True)
try:
    bpy.ops.export_scene.gltf(**kwargs, export_image_format='WEBP')
    img_fmt = 'WEBP'
except TypeError:
    bpy.ops.export_scene.gltf(**kwargs)
    img_fmt = 'PNG'

def glb_summary(path):
    with open(path, 'rb') as f:
        data = f.read()
    ln = struct.unpack_from('<I', data, 12)[0]
    js = json.loads(data[20:20 + ln].decode('utf-8'))
    mats = js.get('materials', [])
    m0 = next((m for m in mats if m.get('name') == 'stone_wall'), {})
    images = js.get('images', [])
    return {
        "bytes": len(data),
        "nodes": len(js.get('nodes', [])),
        "meshes": [m.get('name') for m in js.get('meshes', [])],
        "materials": [m.get('name') for m in mats],
        "stone_wall_pbr": {
            "baseColorTexture": 'baseColorTexture' in m0.get('pbrMetallicRoughness', {}),
            "metallicRoughnessTexture": 'metallicRoughnessTexture' in m0.get('pbrMetallicRoughness', {}),
            "normalTexture": 'normalTexture' in m0,
            "baseColorFactor": m0.get('pbrMetallicRoughness', {}).get('baseColorFactor'),
        },
        "images": [(i.get('name'), i.get('mimeType')) for i in images],
    }

checks = {
    "mesh_named_Walls": walls_me.name == "Walls",
    "bsdf_linked": any(l.from_node.bl_idname == 'ShaderNodeBsdfPrincipled'
                       and l.to_node.bl_idname == 'ShaderNodeOutputMaterial' for l in nt.links),
    "n_nodes": len(nt.nodes),
    "n_links": len(nt.links),
}
summ = glb_summary(glb)
checks["glb_has_textures"] = all(summ["stone_wall_pbr"].get(k)
                                 for k in ("baseColorTexture", "metallicRoughnessTexture", "normalTexture"))
result = {
    "wall_cells": len(wall_cells),
    "verts": len(walls_me.vertices),
    "faces": len(walls_me.polygons),
    "tris": sum(len(p.vertices) - 2 for p in walls_me.polygons),
    "material": mat.name,
    "material_shared_with": other_users,
    "image_format": img_fmt,
    "checks": checks,
    "glb": summ,
    "texture_files": [os.path.getsize(os.path.join(TEX, f)) for f in
                      ("wall_basecolor.png", "wall_normal.png", "wall_rough.png", "wall_orm.png")],
}
