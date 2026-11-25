"""
Unit tests for computational geometry utilities supporting Behaviour Analytics (Phase 8).
Tests distance, heading angles, angular differences with wrap-around, polygon area,
aspect ratio inversion, and spatial clustering.
"""

import math
import pytest
from engines.analytics_engine.geometry import (
    euclidean_distance,
    trajectory_heading_angle,
    angular_difference,
    polygon_area,
    box_aspect_ratio,
    cluster_points,
)


def test_euclidean_distance():
    assert euclidean_distance((0.0, 0.0), (3.0, 4.0)) == pytest.approx(5.0)
    assert euclidean_distance((1.0, 1.0), (1.0, 1.0)) == pytest.approx(0.0)
    assert euclidean_distance((0.5, 0.5), (0.8, 0.9)) == pytest.approx(0.5)


def test_trajectory_heading_angle():
    # In 2D image coordinates (x right, y down):
    # East (moving +x, y unchanged): 0 deg
    assert trajectory_heading_angle((0.0, 0.0), (1.0, 0.0)) == pytest.approx(0.0)
    # South (moving down, +y): 90 deg
    assert trajectory_heading_angle((0.0, 0.0), (0.0, 1.0)) == pytest.approx(90.0)
    # West (moving -x): 180 deg
    assert trajectory_heading_angle((1.0, 0.0), (0.0, 0.0)) == pytest.approx(180.0)
    # North (moving up, -y): 270 deg
    assert trajectory_heading_angle((0.0, 1.0), (0.0, 0.0)) == pytest.approx(270.0)
    # South-East (+x, +y): 45 deg
    assert trajectory_heading_angle((0.0, 0.0), (1.0, 1.0)) == pytest.approx(45.0)


def test_angular_difference_wrap_around():
    # Simple differences
    assert angular_difference(10.0, 40.0) == pytest.approx(30.0)
    assert angular_difference(40.0, 10.0) == pytest.approx(30.0)
    # Identical angles
    assert angular_difference(180.0, 180.0) == pytest.approx(0.0)
    # Wrap-around across 0 / 360 boundary
    assert angular_difference(10.0, 350.0) == pytest.approx(20.0)
    assert angular_difference(355.0, 5.0) == pytest.approx(10.0)
    # Exact opposite angles
    assert angular_difference(0.0, 180.0) == pytest.approx(180.0)
    assert angular_difference(90.0, 270.0) == pytest.approx(180.0)


def test_polygon_area_shoelace():
    # Unit square [0,0] to [1,1]
    square = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    assert polygon_area(square) == pytest.approx(1.0)

    # Right triangle: (0,0), (1,0), (0,1) -> area = 0.5
    triangle = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    assert polygon_area(triangle) == pytest.approx(0.5)

    # Degenerate polygon (< 3 vertices)
    assert polygon_area([(0.0, 0.0), (1.0, 1.0)]) == 0.0


def test_box_aspect_ratio_inversion():
    # Standing upright person: width 0.1, height 0.3 -> ar = 0.33 (< 0.8)
    upright_bbox = (0.4, 0.3, 0.1, 0.3)
    assert box_aspect_ratio(upright_bbox) == pytest.approx(1.0 / 3.0)

    # Fallen / prone person: width 0.3, height 0.1 -> ar = 3.0 (> 1.2)
    prone_bbox = (0.3, 0.5, 0.3, 0.1)
    assert box_aspect_ratio(prone_bbox) == pytest.approx(3.0)

    # Zero height boundary safety
    assert box_aspect_ratio((0.0, 0.0, 0.2, 0.0)) == 0.0


def test_cluster_points_single_linkage():
    # 2 distinct clusters
    # Cluster A: near (0.1, 0.1)
    # Cluster B: near (0.8, 0.8)
    points = [
        (0.10, 0.10),
        (0.12, 0.11),
        (0.11, 0.13),
        (0.80, 0.80),
        (0.82, 0.81),
    ]
    clusters = cluster_points(points, max_distance=0.08)
    assert len(clusters) == 2
    assert len(clusters[0]) == 3
    assert len(clusters[1]) == 2

    # Empty points
    assert cluster_points([]) == []
