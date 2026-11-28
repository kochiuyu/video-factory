"""Drawings for the P1 shape scenes. Manim is imported only when a picture is built."""

from __future__ import annotations

import math

NAVY = "#0B1F3A"
GOLD = "#E0A83A"
GREEN = "#1F8A4C"
CREAM = "#F4E2B0"
SIDE = "#C48A22"

FLAT_KINDS = ("triangle", "quad", "pentagon", "hexagon", "circle")
FLAT_SIDES = {"triangle": 3, "quad": 4, "pentagon": 5, "hexagon": 6, "circle": 0}
SOLID_KINDS = ("prism", "cylinder", "pyramid", "cone", "sphere")
LINE_PARTS = ("marks", "lines", "routes")
JOIN_RESULTS = ("quad", "triangle", "pentagon", "hexagon")


def flat_points(kind: str, radius: float = 1.15) -> list[tuple[float, float, float]]:
    """Vertices of one closed flat shape, starting at the top."""
    count = FLAT_SIDES[kind]
    if count == 0:
        return []
    points = []
    for index in range(count):
        angle = -math.pi / 2 + index * (2 * math.pi / count)
        points.append((radius * math.cos(angle), radius * math.sin(angle), 0.0))
    return points


def _stroke(mob, width=6):
    mob.set_stroke(NAVY, width=width)
    return mob


def flat_picture(kind: str, turn: float = 0):
    """One flat shape. Straight shapes expose ``vf_edges`` for a side count."""
    from manim import Circle, Line, Polygon, VGroup

    if kind == "circle":
        ring = Circle(radius=1.15, color=NAVY, stroke_width=6, fill_color=GOLD, fill_opacity=0.9)
        group = VGroup(ring)
        group.vf_edges = []
        group.vf_fill = ring
    else:
        points = flat_points(kind)
        fill = Polygon(*points, color=NAVY, stroke_width=0, fill_color=GOLD, fill_opacity=0.9)
        edges = []
        for index, start in enumerate(points):
            end = points[(index + 1) % len(points)]
            edge = _stroke(Line(start, end, stroke_width=6))
            edge.set_stroke(opacity=1)
            edges.append(edge)
        group = VGroup(fill, *edges)
        group.vf_edges = edges
        group.vf_fill = fill
    if turn:
        group.rotate(math.radians(turn))
    group.vf_kind = kind
    group.vf_sides = FLAT_SIDES[kind]
    return group


def _round_outline(mob):
    """Stop a stroke at the vertex. A miter join on a sharp corner pokes past it."""
    from manim.constants import CapStyleType, LineJointType

    mob.joint_type = LineJointType.ROUND
    mob.cap_style = CapStyleType.BUTT
    return mob


def _equator_half(front: bool):
    """Front half of a ball's equator is solid. The back half is dashed."""
    from manim import Line, VGroup

    lines = []
    steps = 18
    start = math.pi if front else 0.0
    for index in range(steps):
        if not front and index % 2 == 1:
            continue
        theta0 = start + math.pi * index / steps
        theta1 = start + math.pi * (index + 1) / steps
        a = (0.95 * math.cos(theta0), 0.22 * math.sin(theta0), 0.0)
        b = (0.95 * math.cos(theta1), 0.22 * math.sin(theta1), 0.0)
        lines.append(_round_outline(Line(a, b, color=NAVY, stroke_width=3)))
    return VGroup(*lines)


def solid_picture(kind: str):
    """A simple drawing of one solid. The whole model stays in view, not one face."""
    from manim import Circle, Ellipse, Polygon, Rectangle, VGroup

    faces = []
    if kind == "prism":
        front = _round_outline(Polygon(
            (-0.72, -0.7, 0), (0.72, -0.7, 0), (0.72, 0.55, 0), (-0.72, 0.55, 0),
            color=NAVY, stroke_width=5, fill_color=GOLD, fill_opacity=1,
        ))
        side = _round_outline(Polygon(
            (0.72, -0.7, 0), (1.15, -0.38, 0), (1.15, 0.87, 0), (0.72, 0.55, 0),
            color=NAVY, stroke_width=5, fill_color=SIDE, fill_opacity=1,
        ))
        top = _round_outline(Polygon(
            (-0.72, 0.55, 0), (0.72, 0.55, 0), (1.15, 0.87, 0), (-0.29, 0.87, 0),
            color=NAVY, stroke_width=5, fill_color=CREAM, fill_opacity=1,
        ))
        faces = [side, top, front]
    elif kind == "cylinder":
        body = _round_outline(Rectangle(
            width=1.5, height=1.25, color=NAVY, stroke_width=5, fill_color=GOLD, fill_opacity=1,
        ))
        top = _round_outline(Ellipse(
            width=1.5, height=0.42, color=NAVY, stroke_width=5, fill_color=CREAM, fill_opacity=1,
        ).shift((0, 0.62, 0)))
        bottom = _round_outline(Ellipse(
            width=1.5, height=0.42, color=NAVY, stroke_width=5, fill_color=SIDE, fill_opacity=1,
        ).shift((0, -0.62, 0)))
        faces = [bottom, body, top]
    elif kind == "pyramid":
        base = _round_outline(Polygon(
            (-0.85, -0.55, 0), (0.85, -0.55, 0), (0.45, -0.95, 0), (-1.25, -0.95, 0),
            color=NAVY, stroke_width=5, fill_color=SIDE, fill_opacity=1,
        ))
        left = _round_outline(Polygon(
            (-0.85, -0.55, 0), (0, 0.95, 0), (-1.25, -0.95, 0),
            color=NAVY, stroke_width=5, fill_color=CREAM, fill_opacity=1,
        ))
        right = _round_outline(Polygon(
            (0.85, -0.55, 0), (0, 0.95, 0), (0.45, -0.95, 0),
            color=NAVY, stroke_width=5, fill_color=GOLD, fill_opacity=1,
        ))
        front = _round_outline(Polygon(
            (-0.85, -0.55, 0), (0.85, -0.55, 0), (0, 0.95, 0),
            color=NAVY, stroke_width=5, fill_color=GOLD, fill_opacity=0.95,
        ))
        faces = [base, left, right, front]
    elif kind == "cone":
        body = _round_outline(Polygon(
            (-0.75, -0.45, 0), (0.75, -0.45, 0), (0, 1.05, 0),
            color=NAVY, stroke_width=5, fill_color=GOLD, fill_opacity=1,
        ))
        base = _round_outline(Ellipse(
            width=1.5, height=0.42, color=NAVY, stroke_width=5, fill_color=SIDE, fill_opacity=1,
        ).shift((0, -0.45, 0)))
        faces = [body, base]
    else:
        ball = _round_outline(Circle(
            radius=0.95, color=NAVY, stroke_width=5, fill_color=GOLD, fill_opacity=1,
        ))
        shine = Circle(radius=0.22, color=CREAM, stroke_width=0, fill_color=CREAM, fill_opacity=1)
        shine.shift((-0.28, 0.32, 0))
        faces = [ball, _equator_half(False), _equator_half(True), shine]
    group = VGroup(*faces)
    group.vf_kind = kind
    group.vf_faces = faces
    return group


def join_picture(result: str):
    """Two pieces in their joined places, plus the outside edges and the inside join."""
    from manim import Line, Polygon, VGroup

    if result == "quad":
        a = [(-1.05, -1.0, 0), (1.05, -1.0, 0), (1.05, 1.0, 0)]
        b = [(-1.05, -1.0, 0), (1.05, 1.0, 0), (-1.05, 1.0, 0)]
        outside = [(-1.05, -1.0, 0), (1.05, -1.0, 0), (1.05, 1.0, 0), (-1.05, 1.0, 0)]
        seam = ((-1.05, -1.0, 0), (1.05, 1.0, 0))
    elif result == "triangle":
        a = [(-1.15, -0.95, 0), (0.0, -0.95, 0), (0.0, 1.15, 0)]
        b = [(0.0, -0.95, 0), (1.15, -0.95, 0), (0.0, 1.15, 0)]
        outside = [(-1.15, -0.95, 0), (1.15, -0.95, 0), (0.0, 1.15, 0)]
        seam = ((0.0, -0.95, 0), (0.0, 1.15, 0))
    elif result == "pentagon":
        a = [(-1.15, -0.15, 0), (1.15, -0.15, 0), (0.0, 1.15, 0)]
        b = [(-1.15, -0.15, 0), (1.15, -0.15, 0), (0.85, -1.05, 0), (-0.85, -1.05, 0)]
        outside = [(-1.15, -0.15, 0), (0.0, 1.15, 0), (1.15, -0.15, 0), (0.85, -1.05, 0), (-0.85, -1.05, 0)]
        seam = ((-1.15, -0.15, 0), (1.15, -0.15, 0))
    else:
        a = [(-1.15, 0.0, 0), (-0.55, 0.95, 0), (0.55, 0.95, 0), (1.15, 0.0, 0)]
        b = [(-1.15, 0.0, 0), (1.15, 0.0, 0), (0.55, -0.95, 0), (-0.55, -0.95, 0)]
        outside = [
            (-1.15, 0.0, 0), (-0.55, 0.95, 0), (0.55, 0.95, 0),
            (1.15, 0.0, 0), (0.55, -0.95, 0), (-0.55, -0.95, 0),
        ]
        seam = ((-1.15, 0.0, 0), (1.15, 0.0, 0))

    def piece(points, color):
        mob = Polygon(*points, color=NAVY, stroke_width=4, fill_color=color, fill_opacity=0.95)
        mob.vf_home = mob.get_center()
        return mob

    first = piece(a, GREEN)
    second = piece(b, GOLD)
    edges = []
    for index, start in enumerate(outside):
        end = outside[(index + 1) % len(outside)]
        edge = _stroke(Line(start, end, stroke_width=7))
        edges.append(edge)
    seam_line = Line(seam[0], seam[1], color=NAVY, stroke_width=3)
    seam_line.set_stroke(opacity=0.35)
    group = VGroup(first, second, seam_line, *edges)
    group.vf_pieces = (first, second)
    group.vf_edges = edges
    group.vf_seam = seam_line
    group.vf_sides = len(outside)
    group.vf_result = result
    return group


def straight_line():
    from manim import Line

    return _stroke(Line((-1.6, 0, 0), (1.6, 0, 0), stroke_width=8))


def arc_stroke(start, end, angle: float = 1.05, pieces: int = 24):
    """A curved stroke from start to end. Short lines, so it never fills in."""
    from manim import Line, VGroup

    sx, sy = float(start[0]), float(start[1])
    ex, ey = float(end[0]), float(end[1])
    dx, dy = ex - sx, ey - sy
    chord = math.hypot(dx, dy) or 1.0
    half = abs(angle) / 2.0
    radius = chord / (2.0 * math.sin(half)) if half > 0.05 else chord * 4.0
    mx, my = (sx + ex) / 2.0, (sy + ey) / 2.0
    px, py = -dy / chord, dx / chord
    sign = 1.0 if angle >= 0 else -1.0
    height = math.sqrt(max(radius * radius - (chord / 2.0) ** 2, 0.0))
    cx, cy = mx + sign * px * height, my + sign * py * height
    a0 = math.atan2(sy - cy, sx - cx)
    a1 = math.atan2(ey - cy, ex - cx)
    sweep = a1 - a0
    if sign > 0 and sweep < 0:
        sweep += 2.0 * math.pi
    if sign < 0 and sweep > 0:
        sweep -= 2.0 * math.pi
    points = []
    for index in range(pieces + 1):
        theta = a0 + sweep * index / pieces
        points.append((cx + radius * math.cos(theta), cy + radius * math.sin(theta), 0.0))
    return VGroup(*[
        Line(points[index], points[index + 1], color=NAVY, stroke_width=8)
        for index in range(pieces)
    ])


def curved_line():
    return arc_stroke((-1.55, -0.15, 0.0), (1.55, -0.15, 0.0), angle=1.15)
