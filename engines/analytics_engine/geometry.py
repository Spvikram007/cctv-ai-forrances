"""
Computational Geometry Utilities for Video Analytics.
Provides robust point-in-polygon tests, line segment intersection,
and directional crossing analysis using normalized coordinates [0.0, 1.0].
"""

from typing import List, Tuple, Optional


def box_bottom_center(bbox: Tuple[float, float, float, float]) -> Tuple[float, float]:
    """
    Returns the bottom-center coordinate (ground contact / feet position)
    from a normalized bounding box (x, y, w, h).
    """
    x, y, w, h = bbox
    return (x + (w / 2.0), y + h)


def box_center(bbox: Tuple[float, float, float, float]) -> Tuple[float, float]:
    """
    Returns the geometric center coordinate from a normalized bounding box (x, y, w, h).
    """
    x, y, w, h = bbox
    return (x + (w / 2.0), y + (h / 2.0))


def point_in_polygon(
    point: Tuple[float, float],
    polygon: List[Tuple[float, float]],
) -> bool:
    """
    Tests whether a point (px, py) lies inside a 2D polygon using the Ray Casting algorithm.
    Polygon is defined as a list of (x, y) vertices in clockwise or counter-clockwise order.
    Returns True if inside or on boundary, False otherwise.
    """
    if len(polygon) < 3:
        return False

    px, py = point
    n = len(polygon)
    inside = False

    # Check each edge (p1, p2)
    p1x, p1y = polygon[0]
    for i in range(1, n + 1):
        p2x, p2y = polygon[i % n]

        # Exact vertex match
        if px == p1x and py == p1y:
            return True

        # Check if point is on horizontal edge
        if p1y == p2y == py and min(p1x, p2x) <= px <= max(p1x, p2x):
            return True

        # Check ray intersection with edge
        if (p1y > py) != (p2y > py):
            # Compute x-coordinate of intersection with line y = py
            x_inters = (p2x - p1x) * (py - p1y) / (p2y - p1y) + p1x
            if px == x_inters:
                return True  # Point is exactly on the edge
            if px < x_inters:
                inside = not inside

        p1x, p1y = p2x, p2y

    return inside


def _ccw_orientation(
    a: Tuple[float, float],
    b: Tuple[float, float],
    c: Tuple[float, float],
) -> float:
    """
    Calculates signed area / 2D cross product of vectors AB and BC.
    > 0: Counter-clockwise turn
    < 0: Clockwise turn
    = 0: Collinear
    """
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _on_segment(
    p: Tuple[float, float],
    q: Tuple[float, float],
    r: Tuple[float, float],
) -> bool:
    """Checks if point q lies on segment pr given p, q, r are collinear."""
    return (
        min(p[0], r[0]) <= q[0] <= max(p[0], r[0])
        and min(p[1], r[1]) <= q[1] <= max(p[1], r[1])
    )


def line_segments_intersect(
    p1: Tuple[float, float],
    p2: Tuple[float, float],
    q1: Tuple[float, float],
    q2: Tuple[float, float],
) -> bool:
    """
    Tests if line segment p1-p2 intersects line segment q1-q2.
    """
    o1 = _ccw_orientation(p1, p2, q1)
    o2 = _ccw_orientation(p1, p2, q2)
    o3 = _ccw_orientation(q1, q2, p1)
    o4 = _ccw_orientation(q1, q2, p2)

    # General case: segments straddle each other
    if ((o1 > 0 and o2 < 0) or (o1 < 0 and o2 > 0)) and (
        (o3 > 0 and o4 < 0) or (o3 < 0 and o4 > 0)
    ):
        return True

    # Special collinear cases
    if o1 == 0 and _on_segment(p1, q1, p2):
        return True
    if o2 == 0 and _on_segment(p1, q2, p2):
        return True
    if o3 == 0 and _on_segment(q1, p1, q2):
        return True
    if o4 == 0 and _on_segment(q1, p2, q2):
        return True

    return False


def get_crossing_direction(
    line_start: Tuple[float, float],
    line_end: Tuple[float, float],
    prev_pos: Tuple[float, float],
    curr_pos: Tuple[float, float],
) -> Optional[str]:
    """
    Determines crossing direction when trajectory segment prev_pos -> curr_pos
    crosses virtual line line_start -> line_end.
    
    Orientation convention:
    - Looking along line_start -> line_end:
      A is the left-hand side, B is the right-hand side.
    - If moving from Left to Right: returns "A_TO_B"
    - If moving from Right to Left: returns "B_TO_A"
    - If no crossing: returns None
    """
    if not line_segments_intersect(line_start, line_end, prev_pos, curr_pos):
        return None

    # Sign of orientation of prev_pos with respect to line_start -> line_end
    o_prev = _ccw_orientation(line_start, line_end, prev_pos)
    o_curr = _ccw_orientation(line_start, line_end, curr_pos)

    # In 2D screen coordinates (y down):
    # o > 0 means left side (A), o < 0 means right side (B)
    if o_prev >= 0 and o_curr < 0:
        return "A_TO_B"
    elif o_prev <= 0 and o_curr > 0:
        return "B_TO_A"

    # Default fallback if boundary-aligned
    return "A_TO_B" if o_prev >= o_curr else "B_TO_A"
