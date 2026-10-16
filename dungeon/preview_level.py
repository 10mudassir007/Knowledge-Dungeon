"""One-off level preview renders (corridor + wall close-up) for eyeballing."""
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

OUT = os.path.join(HERE, "level_preview")
os.makedirs(OUT, exist_ok=True)

CELL = 2.0


def aim(obj, loc, target, up=(0, 1, 0)):
    loc = Vector(loc)
    target = Vector(target)
    zaxis = (loc - target).normalized()
    xaxis = Vector(up).cross(zaxis).normalized()
    yaxis = zaxis.cross(xaxis)
    obj.location = loc
    obj.rotation_euler = Matrix((xaxis, yaxis, zaxis)).transposed().to_euler()


scene = bpy.context.scene
cam = bpy.data.objects.get("PreviewCam")
if cam is None:
    cam = bpy.data.objects.new("PreviewCam", bpy.data.cameras.new("PreviewCam"))
    scene.collection.objects.link(cam)
scene.camera = cam
cam.data.lens = 24


def light(name, loc, energy, color, size=3.0):
    ob = bpy.data.objects.get(name)
    if ob is None or ob.type != "LIGHT":
        data = bpy.data.lights.get(name) or bpy.data.lights.new(name, "AREA")
        if ob:
            bpy.data.objects.remove(ob, do_unlink=True)
        ob = bpy.data.objects.new(name, data)
        scene.collection.objects.link(ob)
    ob.data.energy = energy
    ob.data.size = size
    ob.data.color = color
    aim(ob, loc, (loc[0], 0, loc[2]))
    return ob


# spawn is (1, 27) -> world (3, 55); corridor runs east
light("LevelAmb1", (3, 2.6, 55), 90, (0.45, 0.42, 0.75), 6)
light("LevelTorch", (13, 2.0, 55), 300, (1.0, 0.72, 0.42), 2)
light("LevelTorch2", (13, 2.0, 29), 300, (1.0, 0.72, 0.42), 2)
light("LevelAltar", (63, 2.2, 11), 320, (0.72, 0.55, 1.0), 3)

scene.render.engine = "BLENDER_EEVEE"
scene.render.resolution_x, scene.render.resolution_y = 900, 560
scene.render.film_transparent = False
scene.render.image_settings.file_format = "PNG"
scene.view_settings.view_transform = "Standard"
try:
    scene.eevee.taa_render_samples = 24
except Exception:
    pass

shots = [
    ("corridor_spawn.png", (3, 1.65, 55), (20, 1.5, 55)),
    ("wall_closeup.png", (9.5, 1.5, 55), (11.6, 1.5, 55.4)),
    ("wide_hall.png", (3, 1.7, 55), (10, 1.6, 48)),
]
for name, loc, target in shots:
    aim(cam, loc, target)
    cam.data.lens = 24 if "closeup" not in name else 35
    scene.render.filepath = os.path.join(OUT, name)
    bpy.ops.render.render(write_still=True)
    print("SHOT", name, scene.render.filepath)
print("LEVEL PREVIEW DONE")