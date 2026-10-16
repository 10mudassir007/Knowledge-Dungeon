"""Re-import dungeon/dungeon.glb into a fresh scene and verify it.

Run:  blender --background --python verify_export.py
"""

import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import validate_map

GLB_PATH = os.path.join(HERE, "dungeon.glb")

EXPECTED_TORCHES = {(6, 1), (6, 4), (12, 4), (2, 6)}
EXPECTED_LIVES = [(1, 5), (2, 5), (3, 5)]
MAX_TRIANGLES = 150_000
MAX_MATERIALS = 12
MAX_BYTES = 8 * 1024 * 1024


def tri_count(mesh):
    return sum(len(poly.vertices) - 2 for poly in mesh.polygons)


def to_file_space(world):
    """Imported Blender position -> coordinates as stored in the glTF file.

    Blender's glTF importer always rotates glTF (Y-up) into Blender (Z-up):
        blender = (g_x, -g_z, g_y)     so the inverse is   g = (b_x, b_z, -b_y)
    The dungeon is authored Y-up, so checks are expressed in file space.
    """
    x, y, z = world
    return [round(x, 4), round(z, 4), round(-y, 4)]


def check(cond, label, detail, failures):
    if not cond:
        failures.append(f"{label}: {detail}")
    return {"check": label, "ok": bool(cond), "detail": detail}


def main():
    grid = validate_map.load_grid()
    wall_cells = len(validate_map.find(grid, "#"))
    enemy_cells = validate_map.find(grid, "E")

    # Fresh, empty scene (read_homefile is the MCP-safe equivalent).
    bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
    bpy.ops.import_scene.gltf(filepath=GLB_PATH)

    objects = list(bpy.data.objects)
    empties = {o.name: o for o in objects if o.type == "EMPTY"}
    meshes = {o.name: o for o in objects if o.type == "MESH"}

    failures = []
    results = []

    # --- Altar -----------------------------------------------------------
    altar = [n for n in empties if n == "Altar"]
    results.append(check(len(altar) == 1, "exactly one 'Altar' empty", f"found {len(altar)}", failures))
    if altar:
        loc = to_file_space(empties["Altar"].location)
        results.append(
            check(loc == [10.5, 0.0, 6.5], "Altar centre (10.5, 0, 6.5) = cell (10,6)", f"file space {loc}", failures)
        )

    # --- Torches ---------------------------------------------------------
    torch_names = sorted(n for n in empties if n.startswith("Torch_"))
    results.append(check(len(torch_names) == 4, "exactly four Torch_ empties", f"found {len(torch_names)} {torch_names}", failures))
    found_torches = set()
    for name in torch_names:
        try:
            col, row = (int(p) for p in name.removeprefix("Torch_").split("_"))
        except ValueError:
            failures.append(f"Torch name not <col>_<row>: {name}")
            continue
        found_torches.add((col, row))
        obj = empties[name]
        want = [col + 0.5, 1.4, row + 0.5]
        got = to_file_space(obj.location)
        results.append(check(got == want, f"{name} at cell ({col},{row})", f"{got} expected {want}", failures))
    results.append(check(found_torches == EXPECTED_TORCHES, "torch grid coords", f"{sorted(found_torches)}", failures))

    # --- Lectern ---------------------------------------------------------
    lectern = [n for n in empties if n == "Hint_Lectern"]
    results.append(check(len(lectern) == 1, "exactly one Hint_Lectern", f"found {len(lectern)}", failures))
    if lectern:
        loc = to_file_space(empties["Hint_Lectern"].location)
        results.append(check(loc == [1.5, 0.0, 1.5], "Hint_Lectern at cell (1,1)", f"file space {loc} expected [1.5, 0.0, 1.5]", failures))
    results.append(check("Lectern" in meshes, "lectern geometry exported", f"Lectern mesh present: {'Lectern' in meshes}", failures))

    # --- Lives / flames --------------------------------------------------
    life_names = sorted(n for n in empties if n.startswith("Life_"))
    results.append(check(life_names == ["Life_1", "Life_2", "Life_3"], "three Life_ empties", f"{life_names}", failures))
    for index, (col, row) in enumerate(EXPECTED_LIVES, start=1):
        name = f"Life_{index}"
        if name in empties:
            loc = to_file_space(empties[name].location)
            want = [col + 0.5, 0.0, row + 0.5]
            results.append(check(loc == want, f"{name} at cell ({col},{row})", f"file space {loc} expected {want}", failures))
    flame_meshes = sorted(n for n in meshes if n.startswith("Flame_"))
    results.append(check(flame_meshes == ["Flame_1", "Flame_2", "Flame_3"], "matching Flame_ meshes", f"{flame_meshes}", failures))

    # --- Enemies ---------------------------------------------------------
    enemy_names = sorted(n for n in meshes if n.startswith("Enemy_"))
    expected_enemy_names = sorted(f"Enemy_{c}_{r}" for c, r in enemy_cells)
    results.append(check(enemy_names == expected_enemy_names, "one Enemy_ per E cell, named by grid", f"{enemy_names} expected {expected_enemy_names}", failures))

    # --- Walls -----------------------------------------------------------
    # Imported glTF primitives are triangles (3 verts), so a 1x3x1 box that is
    # 6 quads in Blender arrives as 12 triangles.
    wall_tris = tri_count(meshes["Walls"].data) if "Walls" in meshes else 0
    results.append(check(
        wall_tris == wall_cells * 12,
        "wall blocks == '#' cell count",
        f"{wall_tris // 12} blocks ({wall_tris} triangles) vs {wall_cells} wall cells",
        failures,
    ))

    # --- Dungeon stands upright in the file (height along +Y) -------------
    # Height in file space is to_file_space(...)[1]; read it off the vertices.
    if "Ceiling" in meshes and "Floor" in meshes:
        ceil_h = max(to_file_space(v.co)[1] for v in meshes["Ceiling"].data.vertices)
        floor_h = max(to_file_space(v.co)[1] for v in meshes["Floor"].data.vertices)
        results.append(
            check(
                round(ceil_h, 4) == 3.0 and round(floor_h, 4) == 0.0,
                "Y-up: floor at y=0, ceiling at y=3",
                f"file-space floor top y={round(floor_h, 4)}, ceiling y={round(ceil_h, 4)}",
                failures,
            )
        )

    # --- Budgets ---------------------------------------------------------
    total_tris = sum(tri_count(o.data) for o in objects if o.type == "MESH")
    materials = sorted({m.name for o in objects if o.type == "MESH" for m in o.data.materials if m})
    size = os.path.getsize(GLB_PATH)

    results.append(check(total_tris < MAX_TRIANGLES, "triangles under 150,000", f"{total_tris}", failures))
    results.append(check(len(materials) < MAX_MATERIALS, "unique materials under 12", f"{len(materials)} {materials}", failures))
    results.append(check(size <= MAX_BYTES, "file under 8 MB", f"{size/1024/1024:.3f} MB", failures))

    # --- Structure present ----------------------------------------------
    for required in ("Walls", "Floor", "Ceiling", "AltarBlock", "AltarCrystal", "BarrelMesh", "CrateMesh"):
        results.append(check(required in meshes, f"{required} exported", f"present={required in meshes}", failures))
    results.append(check(not any(o.type in {"CAMERA", "LIGHT"} for o in objects), "no cameras or lights", "none found", failures))

    report = {
        "file": GLB_PATH,
        "size_bytes": size,
        "size_mb": round(size / 1024 / 1024, 3),
        "total_triangles": total_tris,
        "unique_materials": materials,
        "object_count": len(objects),
        "empties": sorted(empties),
        "meshes": sorted(meshes),
        "checks": results,
        "failures": failures,
        "passed": not failures,
    }
    print("VERIFY_JSON_START")
    print(json.dumps(report, indent=2))
    print("VERIFY_JSON_END")
    with open(os.path.join(HERE, "verify_report.json"), "w", encoding="utf-8") as handle:
        json.dump(report, handle, indent=2)
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())