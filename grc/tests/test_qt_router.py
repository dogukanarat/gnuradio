"""
Copyright 2026 The GNU Radio Contributors

SPDX-License-Identifier: GPL-2.0-or-later

Tests for the orthogonal connection router of the Qt GUI. The router is
plain Python, so it is loaded straight from its file (no Qt needed).
"""

import importlib.util
import os
import random

_PATH = os.path.join(os.path.dirname(__file__), "..", "gui_qt", "components", "canvas", "router.py")
_spec = importlib.util.spec_from_file_location("grc_qt_router", _PATH)
router = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(router)


def _segments(points):
    return list(zip(points, points[1:]))


def _orthogonal(points):
    return all(abs(a[0] - b[0]) < 1e-6 or abs(a[1] - b[1]) < 1e-6 for a, b in _segments(points))


def _crosses(points, rect):
    left, top, right, bottom = rect
    for (x1, y1), (x2, y2) in _segments(points):
        if abs(y1 - y2) < 1e-6:
            if top < y1 < bottom and min(x1, x2) < right and max(x1, x2) > left:
                return True
        elif left < x1 < right and min(y1, y2) < bottom and max(y1, y2) > top:
            return True
    return False


def _overlap(points, segment):
    (cx, cy), (dx, dy) = segment
    total = 0.0
    for (ax, ay), (bx, by) in _segments(points):
        if abs(ay - by) < 1e-6 and abs(cy - dy) < 1e-6 and abs(ay - cy) < router.LANE - 0.5:
            total += max(0.0, min(max(ax, bx), max(cx, dx)) - max(min(ax, bx), min(cx, dx)))
        if abs(ax - bx) < 1e-6 and abs(cx - dx) < 1e-6 and abs(ax - cx) < router.LANE - 0.5:
            total += max(0.0, min(max(ay, by), max(cy, dy)) - max(min(ay, by), min(cy, dy)))
    return total


def test_straight_line():
    path = router.route((0, 0), (1, 0), (200, 0), (1, 0), [])
    assert path == [(0, 0), (200, 0)]


def test_goes_around_block():
    block = (100, -40, 200, 40)
    path = router.route((0, 0), (1, 0), (300, 0), (1, 0), [block])
    assert path[0] == (0, 0) and path[-1] == (300, 0)
    assert _orthogonal(path)
    assert not _crosses(path, block)


def test_moves_to_free_lane():
    other = ((150, -100), (150, 100))   # vertical line of another output
    path = router.route((0, -50), (1, 0), (300, 50), (1, 0), [], occupied=[other])
    assert _orthogonal(path)
    assert _overlap(path, other) == 0.0


def test_feedback_enters_from_the_left():
    blocks = [(240, -30, 300, 30), (0, -30, 60, 30)]
    path = router.route((300, 0), (1, 0), (0, 0), (1, 0), blocks)
    assert _orthogonal(path)
    assert not any(_crosses(path[1:-1], b) for b in blocks)
    # the last segment arrives moving right
    (x1, y1), (x2, y2) = path[-2], path[-1]
    assert y1 == y2 and x2 > x1


def test_random_layouts_never_cross_blocks():
    rnd = random.Random(1)
    for _ in range(40):
        blocks = []
        for _ in range(6):
            x, y = rnd.uniform(60, 500), rnd.uniform(-200, 200)
            blocks.append((x, y, x + rnd.uniform(30, 90), y + rnd.uniform(20, 60)))
        start = (0.0, rnd.uniform(-150, 150))
        end = (700.0, rnd.uniform(-150, 150))
        path = router.route(start, (1, 0), end, (1, 0), blocks)
        assert path is not None
        assert _orthogonal(path)
        assert not any(_crosses(path, b) for b in blocks)


def test_divergence_point():
    trunk = [(0, 0), (80, 0), (80, -100), (300, -100)]
    assert router.divergence([(0, 0), (150, 0), (150, 100), (300, 100)], [trunk]) == (80.0, 0.0)
    assert router.divergence([(0, 5), (80, 5)], [trunk]) is None


def test_simplify():
    assert router.simplify([(0, 0), (5, 0), (10, 0), (10, 0), (10, 5)]) == [(0, 0), (10, 0), (10, 5)]
