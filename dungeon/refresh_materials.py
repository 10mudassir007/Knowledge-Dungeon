"""Refresh stale material data in dungeon.blend and re-export both GLBs.

History: build_props.ensure_materials() used to create materials only when
missing, so once the .blend was saved with older (near-black) values, every
rebuild kept reusing the stale datablocks - the props rendered black no matter
what the code said. ensure_materials() now rebuilds those trees from the values
in this revision, and this script applies that to the saved .blend directly:

    blender --background dungeon/dungeon.blend --python dungeon/refresh_materials.py

It then re-exports dungeon.glb + puddle.glb (from the refreshed materials),
saves the .blend, and writes refresh_result.json with an audit of the actual
base-colour values that left the file.
"""

import json
import os
import struct
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import build_level
import build_props


def glb_material_audit(path):
    """Material names + their exported base colour/metallic/roughness."""
    with open(path, "rb") as f:
        data = f.read()
    ln = struct.unpack_from("<I", data, 12)[0]
    js = json.loads(data[20:20 + ln].decode("utf-8"))
    audit = {}
    for m in js.get("materials", []):
        pbr = m.get("pbrMetallicRoughness", {})
        col = pbr.get("baseColorFactor")
        audit[m.get("name")] = {
            "base": [round(v, 4) for v in col] if col else None,
            "metallic": round(pbr.get("metallicFactor", 1.0), 3),
            "roughness": round(pbr.get("roughnessFactor", 1.0), 3),
        }
    return audit


def main():
    # 1. The fix itself: rebuild every prop_* material tree from source values.
    mats = build_props.ensure_materials()

    # 2. Re-export the puddle with its (existing) water material.
    water = bpy.data.materials.get("water_puddle")
    if water is None:  # a fresh .blend without water yet
        water = build_level.principled("water_puddle", (0.012, 0.022, 0.030), rough=0.035)
    puddle = build_level.export_puddle({"water_puddle": water})

    # 3. Re-export the level; the pass applies present material state, including
    #    the refreshed props and the already-baked wall images.
    summary, fmt = build_level.export_level()

    # 4. Persist the fixed datablocks so future builds do not regress.
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(HERE, "dungeon.blend"))

    result = {
        "puddle": puddle,
        "glb": summary,
        "image_format": fmt,
        "materials": glb_material_audit(os.path.join(HERE, "dungeon.glb")),
        "blend_saved": os.path.getsize(os.path.join(HERE, "dungeon.blend")),
    }
    out = os.path.join(HERE, "refresh_result.json")
    with open(out, "w") as f:
        json.dump(result, f, indent=1, default=str)
    print("REFRESH RESULT", json.dumps(result, indent=1, default=str))


main()
