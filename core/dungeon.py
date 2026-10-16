"""The Blender-built dungeon, as game data.

Reads `dungeon/map.txt` - the same file `dungeon/build_dungeon.py` builds the
3D model from - so the game rules and the geometry can never drift apart.

World space matches the Blender build exactly:

    column c -> X = c        row r -> Z = r        height -> Y
    cell centre = (c + 0.5, y, r + 0.5)

Anchor names match the objects/empties created by the build script, so a client
can look up "Altar", "Torch_6_1", "Life_1", "Enemy_3_3" ... as glTF nodes.
"""

import json
import os
import struct
from dataclasses import dataclass
from typing import Optional

DUNGEON_DIR = os.environ.get("DUNGEON_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dungeon"
)
MAP_PATH = os.path.join(DUNGEON_DIR, "map.txt")
MODEL_PATH = os.path.join(DUNGEON_DIR, "dungeon.glb")

# Heights the build script uses, kept in one place.
TORCH_HEIGHT = 1.4
CRYSTAL_HEIGHT = 1.4

CELL_KINDS = {
    "#": "wall",
    ".": "floor",
    "Q": "altar",
    "H": "hint",
    "B": "life",
    "T": "torch",
    "E": "enemy",
}


class DungeonUnavailable(RuntimeError):
    """The dungeon map or model is missing/unreadable. Maps to HTTP 503."""


@dataclass(frozen=True)
class Marker:
    """A named point of interest, in both grid and world space."""

    kind: str
    col: int
    row: int
    node: str
    y: float = 0.0
    index: Optional[int] = None

    @property
    def position(self) -> dict:
        return {"x": self.col + 0.5, "y": self.y, "z": self.row + 0.5}

    def as_dict(self) -> dict:
        data = {
            "kind": self.kind,
            "cell": {"col": self.col, "row": self.row},
            "position": self.position,
            "node": self.node,
        }
        if self.index is not None:
            data["index"] = self.index
        return data


class DungeonMap:
    """Parsed dungeon: the grid plus every gameplay marker on it."""

    def __init__(self, rows, markers, altar_path):
        self.rows = list(rows)
        self.width = max(len(r) for r in self.rows) if self.rows else 0
        self.height = len(self.rows)
        self.altar_path = [tuple(cell) for cell in altar_path]

        self.markers = markers
        self.altar = next((m for m in markers if m.kind == "altar"), None)
        self.lectern = next((m for m in markers if m.kind == "hint"), None)
        self.torches = [m for m in markers if m.kind == "torch"]
        self.lives = [m for m in markers if m.kind == "life"]
        self.enemies = [m for m in markers if m.kind == "enemy"]

    # -- geometry helpers ---------------------------------------------------
    @staticmethod
    def cell_center(col, row, y=0.0):
        return {"x": col + 0.5, "y": y, "z": row + 0.5}

    def is_wall(self, col, row) -> bool:
        if 0 <= row < self.height and 0 <= col < len(self.rows[row]):
            return self.rows[row][col] == "#"
        return True  # outside the grid is solid

    @property
    def wall_cells(self) -> int:
        return sum(row.count("#") for row in self.rows)

    @property
    def walkable_cells(self) -> int:
        return self.width * self.height - self.wall_cells

    @property
    def spawn(self) -> Optional[Marker]:
        """Where a player starts: the lectern cell at the head of the path."""
        return self.lectern

    def anchor_names(self):
        """Every glTF node name the game expects the model to provide."""
        names = set()
        for marker in self.markers:
            names.add(marker.node)
            if marker.kind == "life" and marker.index is not None:
                names.add(f"Flame_{marker.index}")
        names.add("Walls")
        names.add("Floor")
        names.add("Ceiling")
        return names

    # -- serialisation ------------------------------------------------------
    def as_dict(self, include_grid=True) -> dict:
        data = {
            "width": self.width,
            "height": self.height,
            "cell_size": 1.0,
            "up_axis": "Y",
            "origin": "top_left",
            "wall_cells": self.wall_cells,
            "walkable_cells": self.walkable_cells,
            "bounds": {
                "min": {"x": 0.0, "y": 0.0, "z": 0.0},
                "max": {"x": float(self.width), "y": 3.0, "z": float(self.height)},
            },
            "altar_path": [{"col": c, "row": r} for c, r in self.altar_path],
            "spawn": self.spawn.as_dict() if self.spawn else None,
            "altar": self.altar.as_dict() if self.altar else None,
            "lectern": self.lectern.as_dict() if self.lectern else None,
            "torches": [m.as_dict() for m in self.torches],
            "lives": [m.as_dict() for m in self.lives],
            "enemies": [m.as_dict() for m in self.enemies],
        }
        if include_grid:
            data["grid"] = self.rows
        return data


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def _find(rows, char):
    return sorted((c, r) for r, row in enumerate(rows) for c, ch in enumerate(row) if ch == char)


def _altar_path(rows, start, goal):
    """Shortest walkable route from the lectern to the altar (4-neighbour BFS)."""
    height = len(rows)

    def walkable(col, row):
        return 0 <= row < height and 0 <= col < len(rows[row]) and rows[row][col] != "#"

    if not walkable(*start) or not walkable(*goal):
        return []

    from collections import deque

    queue = deque([(start, [start])])
    seen = {start}
    while queue:
        current, path = queue.popleft()
        if current == goal:
            return path
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (current[0] + dx, current[1] + dz)
            if walkable(*nxt) and nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, path + [nxt]))
    return []


def parse_dungeon(rows) -> DungeonMap:
    markers = []

    altar_cell = _find(rows, "Q")
    for col, row in altar_cell:
        markers.append(Marker("altar", col, row, "Altar"))

    hint_cell = _find(rows, "H")
    for col, row in hint_cell:
        markers.append(Marker("hint", col, row, "Hint_Lectern"))

    for col, row in _find(rows, "T"):
        markers.append(Marker("torch", col, row, f"Torch_{col}_{row}", y=TORCH_HEIGHT))

    for index, (col, row) in enumerate(_find(rows, "B"), start=1):
        markers.append(Marker("life", col, row, f"Life_{index}", index=index))

    for col, row in _find(rows, "E"):
        markers.append(Marker("enemy", col, row, f"Enemy_{col}_{row}"))

    path = _altar_path(rows, hint_cell[0] if hint_cell else (0, 0), altar_cell[0] if altar_cell else (0, 0))
    return DungeonMap(rows, markers, path)


def load_dungeon(path=MAP_PATH) -> DungeonMap:
    """Read and parse the dungeon map. Raises DungeonUnavailable if missing."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            rows = [line for line in handle.read().splitlines() if line.strip()]
    except OSError as exc:
        raise DungeonUnavailable(f"Dungeon map not found at {path}") from exc

    if not rows:
        raise DungeonUnavailable(f"Dungeon map at {path} is empty")

    width = max(len(row) for row in rows)
    if any(len(row) != width for row in rows):
        raise DungeonUnavailable(f"Dungeon map at {path} has ragged rows")

    return parse_dungeon(rows)


def model_info(path=MODEL_PATH) -> dict:
    """Metadata about the exported GLB. Never raises for a missing file."""
    if not os.path.exists(path):
        return {"available": False, "url": "/dungeon/model.glb", "format": "glb"}
    return {
        "available": True,
        "url": "/dungeon/model.glb",
        "format": "glb",
        "bytes": os.path.getsize(path),
    }


# ---------------------------------------------------------------------------
# GLB introspection (stdlib only - no Blender needed)
# ---------------------------------------------------------------------------
def glb_node_names(path=MODEL_PATH):
    """Node names inside a .glb, read straight from its JSON chunk.

    Used by the tests to prove the API's anchor names really exist in the
    exported model.
    """
    if not os.path.exists(path):
        raise DungeonUnavailable(f"Dungeon model not found at {path}")

    with open(path, "rb") as handle:
        data = handle.read()

    magic, version, total = struct.unpack("<III", data[:12])
    if magic != 0x46546C67:  # b'glTF'
        raise DungeonUnavailable(f"{path} is not a glb file")

    offset = 12
    while offset < min(total, len(data)):
        chunk_length, chunk_type = struct.unpack("<II", data[offset : offset + 8])
        if chunk_type == 0x4E4F534A:  # b'JSON'
            gltf = json.loads(data[offset + 8 : offset + 8 + chunk_length].decode("utf-8"))
            return [node.get("name", "") for node in gltf.get("nodes", [])]
        offset += 8 + chunk_length

    raise DungeonUnavailable(f"{path} has no JSON chunk")