"""
Copyright 2026 The GNU Radio Contributors
This file is part of GNU Radio

SPDX-License-Identifier: GPL-2.0-or-later

Orthogonal connection router.

Finds a path made of horizontal and vertical segments between two ports,
the way Simulink draws signal lines:

- the path never runs through a block,
- it never runs on top of a line that comes from a different output
  (such lines are moved to a parallel lane, so no line hides another one),
- crossing another line is allowed but costs a little,
- every bend costs a little, so paths stay simple,
- running along a line from the *same* output is cheap, so branches of one
  output grow into a tree.

The router works on plain tuples so it can be used and tested without Qt.
Points are (x, y), directions are unit tuples such as (1, 0), rectangles are
(left, top, right, bottom) and segments are ((x1, y1), (x2, y2)).
"""

import heapq

# Distance between two parallel lines that must not overlap
LANE = 8.0
# Cost of one bend, in units of path length
BEND_COST = 30.0
# Cost of crossing a line of another output
CROSS_COST = 8.0
# Cost per unit length of running on top of a line of another output
OVERLAP_COST = 40.0
# Length multiplier when running along a line of the same output
SHARE_FACTOR = 0.35
# How far beyond the end points the router looks for a way around
SEARCH_MARGIN = 300.0
# Upper bound of grid nodes; above it the extra centre lines are dropped
MAX_NODES = 40000

_DIRS = ((1, 0), (-1, 0), (0, 1), (0, -1))


def _inside(x, y, rect):
    left, top, right, bottom = rect
    return left < x < right and top < y < bottom


def _split(segments):
    """Split segments into horizontal (y, x1, x2) and vertical (x, y1, y2) lists."""
    hor, ver = [], []
    for (x1, y1), (x2, y2) in segments:
        if abs(y1 - y2) < 1e-6 and abs(x1 - x2) > 1e-6:
            hor.append((y1, min(x1, x2), max(x1, x2)))
        elif abs(x1 - x2) < 1e-6 and abs(y1 - y2) > 1e-6:
            ver.append((x1, min(y1, y2), max(y1, y2)))
    return hor, ver


def _overlap(a1, a2, b1, b2):
    return max(0.0, min(a2, b2) - max(a1, b1))


class _Costs:
    """Cost of one straight grid edge against existing lines."""

    def __init__(self, occupied, shared):
        self.occ_h, self.occ_v = _split(occupied)
        self.shr_h, self.shr_v = _split(shared)

    def edge(self, x1, y1, x2, y2):
        length = abs(x2 - x1) + abs(y2 - y1)
        cost = length
        if y1 == y2:                                   # horizontal edge
            lo, hi = min(x1, x2), max(x1, x2)
            for oy, a, b in self.occ_h:
                if abs(oy - y1) < LANE - 0.5:
                    cost += OVERLAP_COST * _overlap(lo, hi, a, b)
            for ox, a, b in self.occ_v:
                if lo < ox < hi and a < y1 < b:
                    cost += CROSS_COST
            for sy, a, b in self.shr_h:
                if abs(sy - y1) < 0.5:
                    cost -= (1.0 - SHARE_FACTOR) * _overlap(lo, hi, a, b)
        else:                                          # vertical edge
            lo, hi = min(y1, y2), max(y1, y2)
            for ox, a, b in self.occ_v:
                if abs(ox - x1) < LANE - 0.5:
                    cost += OVERLAP_COST * _overlap(lo, hi, a, b)
            for oy, a, b in self.occ_h:
                if lo < oy < hi and a < x1 < b:
                    cost += CROSS_COST
            for sx, a, b in self.shr_v:
                if abs(sx - x1) < 0.5:
                    cost -= (1.0 - SHARE_FACTOR) * _overlap(lo, hi, a, b)
        return max(cost, length * SHARE_FACTOR)


def _axis_values(fixed, obstacles, occupied_axis, low, high, with_centres):
    """Grid coordinates along one axis."""
    values = set(fixed)
    edges = set()
    for a, b in obstacles:
        edges.add(a)
        edges.add(b)
    values |= edges
    if with_centres:
        ordered = sorted(edges | set(fixed))
        for a, b in zip(ordered, ordered[1:]):
            if b - a > 2 * LANE:
                values.add((a + b) / 2.0)
    # parallel lanes next to existing lines
    for v in occupied_axis:
        values.add(v + LANE)
        values.add(v - LANE)
    values.add(low)
    values.add(high)
    return sorted(v for v in values if low <= v <= high)


def simplify(points):
    """Drop repeated and collinear intermediate points."""
    out = []
    for p in points:
        if out and abs(p[0] - out[-1][0]) < 1e-6 and abs(p[1] - out[-1][1]) < 1e-6:
            continue
        if len(out) >= 2:
            a, b = out[-2], out[-1]
            if (abs(a[0] - b[0]) < 1e-6 and abs(b[0] - p[0]) < 1e-6) or \
               (abs(a[1] - b[1]) < 1e-6 and abs(b[1] - p[1]) < 1e-6):
                out[-1] = p
                continue
        out.append(p)
    return out


def route(start, start_dir, end, end_dir, obstacles, occupied=(), shared=(), stub=11.0):
    """
    Orthogonal path from `start` to `end`.

    start_dir: direction the line leaves `start` (None: any direction).
    end_dir:   direction the line has when it reaches `end`.
    obstacles: block rectangles the path must not enter.
    occupied:  segments of lines from other outputs (avoid running on them).
    shared:    segments of lines from the same output (cheap to run along).

    Returns the list of points (start and end included), or None.
    """
    sx, sy = start
    ex, ey = end
    if start_dir is not None:
        s1 = (sx + start_dir[0] * stub, sy + start_dir[1] * stub)
    else:
        s1 = start
    e1 = (ex - end_dir[0] * stub, ey - end_dir[1] * stub)

    # Only look at the neighbourhood of the two ends
    left = min(s1[0], e1[0]) - SEARCH_MARGIN
    right = max(s1[0], e1[0]) + SEARCH_MARGIN
    top = min(s1[1], e1[1]) - SEARCH_MARGIN
    bottom = max(s1[1], e1[1]) + SEARCH_MARGIN
    rects = [r for r in obstacles if r[2] > left and r[0] < right and r[3] > top and r[1] < bottom]
    # A block that covers one of the end stubs cannot be avoided; ignore it
    rects = [r for r in rects if not _inside(s1[0], s1[1], r) and not _inside(e1[0], e1[1], r)]
    if rects:
        left = min(left, min(r[0] for r in rects) - 2 * LANE)
        right = max(right, max(r[2] for r in rects) + 2 * LANE)
        top = min(top, min(r[1] for r in rects) - 2 * LANE)
        bottom = max(bottom, max(r[3] for r in rects) + 2 * LANE)

    def near(segment):
        (x1, y1), (x2, y2) = segment
        return max(x1, x2) >= left and min(x1, x2) <= right and max(y1, y2) >= top and min(y1, y2) <= bottom

    occupied = [s for s in occupied if near(s)]
    shared = [s for s in shared if near(s)]
    occ_h, occ_v = _split(occupied)

    xs = ys = None
    for with_centres in (True, False):
        xs = _axis_values((s1[0], e1[0]), [(r[0], r[2]) for r in rects], [v[0] for v in occ_v],
                          left, right, with_centres)
        ys = _axis_values((s1[1], e1[1]), [(r[1], r[3]) for r in rects], [h[0] for h in occ_h],
                          top, bottom, with_centres)
        if len(xs) * len(ys) <= MAX_NODES:
            break

    xi = {x: i for i, x in enumerate(xs)}
    yi = {y: i for i, y in enumerate(ys)}
    nx, ny = len(xs), len(ys)

    blocked_cache = {}

    def blocked(i, j):
        key = (i, j)
        if key not in blocked_cache:
            x, y = xs[i], ys[j]
            blocked_cache[key] = any(_inside(x, y, r) for r in rects)
        return blocked_cache[key]

    def edge_blocked(x1, y1, x2, y2):
        mx, my = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        return any(_inside(mx, my, r) for r in rects)

    costs = _Costs(occupied, shared)
    start_node = (xi[s1[0]], yi[s1[1]])
    goal = (xi[e1[0]], yi[e1[1]])
    first_dirs = [start_dir] if start_dir is not None else list(_DIRS)

    def heuristic(i, j):
        return abs(xs[i] - e1[0]) + abs(ys[j] - e1[1])

    # A* over (node, direction of travel)
    frontier = []
    best = {}
    parent = {}
    counter = 0
    for d in first_dirs:
        state = (start_node, d)
        best[state] = 0.0
        heapq.heappush(frontier, (heuristic(*start_node), counter, 0.0, state))
        counter += 1

    end_state = None
    while frontier:
        _, _, g, state = heapq.heappop(frontier)
        if g > best.get(state, float("inf")) + 1e-9:
            continue
        (i, j), d = state
        if (i, j) == goal:
            if d == end_dir:
                end_state = state
                break
            if d == (-end_dir[0], -end_dir[1]):
                continue
            # turn onto the end stub
            final = (goal, end_dir)
            ng = g + BEND_COST
            if ng < best.get(final, float("inf")):
                best[final] = ng
                parent[final] = state
                heapq.heappush(frontier, (ng, counter, ng, final))
                counter += 1
            continue
        for nd in _DIRS:
            if nd == (-d[0], -d[1]):
                continue
            ni, nj = i + nd[0], j + nd[1]
            if not (0 <= ni < nx and 0 <= nj < ny) or blocked(ni, nj):
                continue
            x1, y1, x2, y2 = xs[i], ys[j], xs[ni], ys[nj]
            if edge_blocked(x1, y1, x2, y2):
                continue
            ng = g + costs.edge(x1, y1, x2, y2) + (BEND_COST if nd != d else 0.0)
            nstate = ((ni, nj), nd)
            if ng < best.get(nstate, float("inf")) - 1e-9:
                best[nstate] = ng
                parent[nstate] = state
                heapq.heappush(frontier, (ng + heuristic(ni, nj), counter, ng, nstate))
                counter += 1

    if end_state is None:
        return None

    nodes = []
    state = end_state
    while state is not None:
        nodes.append(state[0])
        state = parent.get(state)
    nodes.reverse()
    points = [start] + [(xs[i], ys[j]) for i, j in nodes] + [end]
    return simplify(points)


def divergence(points, others, tol=0.5):
    """
    Point where the polyline `points` leaves the polylines `others`, walking
    from its start; None if it does not run along any of them.
    """
    if not others or len(points) < 2:
        return None
    last = None
    for (x1, y1), (x2, y2) in zip(points, points[1:]):
        length = abs(x2 - x1) + abs(y2 - y1)
        if length < 1e-6:
            continue
        horizontal = abs(y1 - y2) < 1e-6
        a0, a1 = (x1, x2) if horizontal else (y1, y2)
        sign = 1.0 if a1 >= a0 else -1.0
        # intervals of this segment (as distance from its start) that lie on another line
        intervals = []
        for other in others:
            for (u1, v1), (u2, v2) in zip(other, other[1:]):
                if horizontal and abs(v1 - v2) < 1e-6 and abs(v1 - y1) < tol:
                    b0, b1 = u1, u2
                elif not horizontal and abs(u1 - u2) < 1e-6 and abs(u1 - x1) < tol:
                    b0, b1 = v1, v2
                else:
                    continue
                t0, t1 = sorted(((b0 - a0) * sign, (b1 - a0) * sign))
                if t1 > 0 and t0 < length:
                    intervals.append((t0, t1))
        covered = 0.0
        for t0, t1 in sorted(intervals):
            if t0 > covered + tol:
                break
            covered = max(covered, t1)
        covered = min(covered, length)
        if covered >= length - tol:
            last = (x2, y2)
            continue
        if covered <= tol:
            return last
        return (x1 + (x2 - x1) * covered / length, y1 + (y2 - y1) * covered / length)
    return last
