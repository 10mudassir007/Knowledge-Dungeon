"""Validate dungeon/map.txt against the expected layout.

Run standalone:  python dungeon/validate_map.py
Also imported by build_dungeon.py.
"""

import os
from collections import deque

HERE = os.path.dirname(os.path.abspath(__file__))
MAP_PATH = os.path.join(HERE, "map.txt")

WIDTH = 15
HEIGHT = 8

EXPECTED = {
    "H": [(1, 1)],
    "Q": [(10, 6)],
    "B": [(1, 5), (2, 5), (3, 5)],
    "T": [(6, 1), (6, 4), (12, 4), (2, 6)],
    "E": [(3, 3), (8, 3)],  # (8,3) is the added second enemy - see ADDED_ENEMY
}

# The one cell added to the author's grid to satisfy "exactly 2 E cells".
# (8,3) is an open hall cell: off the altar path and clear of walls on all sides.
ADDED_ENEMY = (8, 3)


def load_grid(path=MAP_PATH):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read().splitlines()


def find(grid, char):
    return sorted(
        (c, r)
        for r, row in enumerate(grid)
        for c, ch in enumerate(row)
        if ch == char
    )


def walkable(grid):
    return {
        (c, r)
        for r, row in enumerate(grid)
        for c, ch in enumerate(row)
        if ch != "#"
    }


def altar_path(grid, start=(1, 1), goal=(10, 6)):
    """Shortest walkable route from the hint lectern to the altar."""
    cells = walkable(grid)
    if start not in cells or goal not in cells:
        return []
    queue = deque([(start, [start])])
    seen = {start}
    while queue:
        current, path = queue.popleft()
        if current == goal:
            return path
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (current[0] + dx, current[1] + dz)
            if nxt in cells and nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, path + [nxt]))
    return []


def validate(grid):
    """Return (errors, info). Never raises; reports everything it finds."""
    errors = []
    info = {}

    if len(grid) != HEIGHT:
        errors.append(f"row count: expected {HEIGHT}, got {len(grid)}")

    for index, row in enumerate(grid):
        if len(row) != WIDTH:
            errors.append(f"row {index}: expected {WIDTH} chars, got {len(row)} -> {row!r}")

    if errors:
        return errors, info

    walls = find(grid, "#")
    info["walls"] = len(walls)
    info["walkable"] = WIDTH * HEIGHT - len(walls)

    for char, expected in EXPECTED.items():
        actual = find(grid, char)
        info[char] = actual
        if len(actual) != len(expected):
            errors.append(f"'{char}': expected {len(expected)} at {sorted(expected)}, got {len(actual)} at {actual}")
        elif set(actual) != set(expected):
            errors.append(f"'{char}': expected at {sorted(expected)}, got {actual}")

    # Enemies and braziers should not sit on the route to the altar.
    # (H and Q are the path's endpoints, so they are expected to be on it.)
    path = altar_path(grid)
    info["altar_path"] = path
    info["off_path"] = sorted(walkable(grid) - set(path))
    if not path:
        errors.append("altar: no walkable path from the H cell to the Q cell")

    for char in ("E", "B"):
        for cell_pos in info.get(char, []):
            if cell_pos in set(path):
                errors.append(f"'{char}' at {cell_pos} sits on the altar path {path}")

    return errors, info


if __name__ == "__main__":
    grid = load_grid()
    errors, info = validate(grid)
    print(f"map: {MAP_PATH}")
    for i, row in enumerate(grid):
        print(f"  row {i}: len={len(row):2d}  {row}")
    print()
    print(f"walls (#)      : {info.get('walls')}")
    print(f"walkable cells : {info.get('walkable')}")
    for char in "HQBTE":
        print(f"'{char}' cells    : {info.get(char)}")
    print()
    print(f"altar path ({len(info.get('altar_path', []))} cells): {info.get('altar_path')}")
    print(f"off-path floor cells: {len(info.get('off_path', []))}")
    print()
    if errors:
        print("FAILED:")
        for err in errors:
            print("  -", err)
        raise SystemExit(1)
    print("VALID - all expectations met")