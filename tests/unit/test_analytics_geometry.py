"""
Unit Tests for Computational Geometry Utilities in Video Analytics.
Verifies point-in-polygon, segment intersection, directional analysis, and bounding box conversions.
"""

import pytest
from engines.analytics_engine.geometry import (
    point_in_polygon,
    line_segments_intersect,
    get_crossing_direction,
    box_bottom_center,
    box_center,
)


def test_box_bottom_center_and_center():
    # bbox format: (x, y, w, h)
    bbox = (0.2, 0.3, 0.1, 0.4)
    bc = box_bottom_center(bbox)
    # bottom center = (0.2 + 0.05, 0.3 + 0.4) = (0.25, 0.7)
    assert abs(bc[0] - 0.25) < 1e-5
    assert abs(bc[1] - 0.70) < 1e-5

    c = box_center(bbox)
    # center = (0.2 + 0.05, 0.3 + 0.2) = (0.25, 0.5)
    assert abs(c[0] - 0.25) < 1e-5
    assert abs(c[1] - 0.50) < 1e-5


def test_point_in_polygon_convex_and_concave():
    # Square polygon: (0.2, 0.2) to (0.8, 0.8)
    square = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]

    # Strictly inside
    assert point_in_polygon((0.5, 0.5), square) is True
    assert point_in_polygon((0.21, 0.21), square) is True

    # Strictly outside
    assert point_in_polygon((0.1, 0.5), square) is False
    assert point_in_polygon((0.9, 0.5), square) is False
    assert point_in_polygon((0.5, 0.1), square) is False
    assert point_in_polygon((0.5, 0.9), square) is False

    # Vertices and edges (boundary inclusive)
    assert point_in_polygon((0.2, 0.2), square) is True
    assert point_in_polygon((0.5, 0.2), square) is True

    # L-shaped Concave Polygon:
    # (0,0) -> (4,0) -> (4,2) -> (2,2) -> (2,4) -> (0,4)
    l_poly = [(0.0, 0.0), (0.4, 0.0), (0.4, 0.2), (0.2, 0.2), (0.2, 0.4), (0.0, 0.4)]
    assert point_in_polygon((0.1, 0.1), l_poly) is True
    assert point_in_polygon((0.1, 0.3), l_poly) is True
    assert point_in_polygon((0.3, 0.1), l_poly) is True
    # Inside bounding box of L but outside the concave polygon
    assert point_in_polygon((0.3, 0.3), l_poly) is False


def test_line_segments_intersect():
    # Crossing X pattern
    p1, p2 = (0.0, 0.0), (1.0, 1.0)
    q1, q2 = (0.0, 1.0), (1.0, 0.0)
    assert line_segments_intersect(p1, p2, q1, q2) is True

    # Parallel non-intersecting lines
    l1_start, l1_end = (0.1, 0.1), (0.9, 0.1)
    l2_start, l2_end = (0.1, 0.2), (0.9, 0.2)
    assert line_segments_intersect(l1_start, l1_end, l2_start, l2_end) is False

    # T-junction intersection
    h_start, h_end = (0.0, 0.5), (1.0, 0.5)
    v_start, v_end = (0.5, 0.0), (0.5, 0.5)
    assert line_segments_intersect(h_start, h_end, v_start, v_end) is True

    # Collinear non-overlapping
    assert line_segments_intersect((0.0, 0.0), (0.2, 0.2), (0.3, 0.3), (0.5, 0.5)) is False


def test_get_crossing_direction():
    # Virtual line from left to right: (0.1, 0.5) -> (0.9, 0.5)
    # In screen coordinates (y positive downwards):
    # Looking from (0.1, 0.5) towards (0.9, 0.5):
    # Top (y < 0.5) is Side A (left), Bottom (y > 0.5) is Side B (right).
    line_start = (0.1, 0.5)
    line_end = (0.9, 0.5)

    # Motion from top to bottom (y: 0.3 -> 0.7)
    prev_pos = (0.5, 0.3)
    curr_pos = (0.5, 0.7)
    dir_ab = get_crossing_direction(line_start, line_end, prev_pos, curr_pos)
    assert dir_ab in ("A_TO_B", "B_TO_A")

    # Reverse motion from bottom to top (y: 0.7 -> 0.3)
    prev_rev = (0.5, 0.7)
    curr_rev = (0.5, 0.3)
    dir_ba = get_crossing_direction(line_start, line_end, prev_rev, curr_rev)
    assert dir_ba in ("A_TO_B", "B_TO_A")
    assert dir_ab != dir_ba  # Opposite directions must produce complementary direction labels

    # Motion that does not cross the line
    no_cross_prev = (0.5, 0.2)
    no_cross_curr = (0.5, 0.4)
    assert get_crossing_direction(line_start, line_end, no_cross_prev, no_cross_curr) is None
