"""Drawings for the P1 everyday-maths scenes.

Manim is imported only when a picture is built. Lengths, coins, and clocks
do not fit the number or shape scenes, so they live here.
"""

from __future__ import annotations

import calendar
import math

from shape_draw import CREAM, GOLD, GREEN, NAVY, SIDE, _round_outline

COIN_VALUES = (10, 20, 50, 100, 200, 500, 1000)
WEEKDAYS = {
    "en": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "zh": ["一", "二", "三", "四", "五", "六", "日"],
    "zh_hk": ["一", "二", "三", "四", "五", "六", "日"],
}


def coin_face(cents: int) -> str:
    """The numeral printed on a labelled token. Not a real coin."""
    if cents >= 100 and cents % 100 == 0:
        return f"${cents // 100}"
    return f"{cents}¢"


def price_text(cents: int) -> str:
    return f"${cents // 100}.{cents % 100:02d}"


def _bind_directions():
    """Manim directions, bound once a picture is actually built."""
    global DOWN, LEFT, RIGHT, UP
    import manim

    DOWN = manim.DOWN
    LEFT = manim.LEFT
    RIGHT = manim.RIGHT
    UP = manim.UP


def _fresh(group):
    group.vf_later = []
    group.vf_strokes = []
    group.vf_align = None
    group.vf_marked = None
    return group


def _bar(width: float, height: float = 0.42):
    from manim import Rectangle

    bar = Rectangle(
        width=max(0.24, float(width)),
        height=height,
        color=NAVY,
        stroke_width=5,
        fill_color=GOLD,
        fill_opacity=0.95,
    )
    return _round_outline(bar)


def _pip(color: str = GOLD, radius: float = 0.12):
    from manim import Circle

    return Circle(
        radius=radius,
        color=NAVY,
        stroke_width=3,
        fill_color=color,
        fill_opacity=1,
    )


def _square(side: float):
    from manim import Square

    tile = Square(
        side_length=side,
        color=NAVY,
        stroke_width=4,
        fill_color=GOLD,
        fill_opacity=0.95,
    )
    return _round_outline(tile)


def _cell(label, fill: str = CREAM, min_w: float = 0.7, min_h: float = 0.58):
    from manim import RoundedRectangle, VGroup

    box = RoundedRectangle(
        width=max(min_w, float(label.width) + 0.28),
        height=max(min_h, float(label.height) + 0.22),
        corner_radius=0.08,
        color=NAVY,
        stroke_width=4,
        fill_color=fill,
        fill_opacity=1,
    )
    _round_outline(box)
    label.move_to(box)
    cell = VGroup(box, label)
    cell.vf_box = box
    return cell


def _blank_cell(width: float, height: float):
    from manim import RoundedRectangle

    box = RoundedRectangle(
        width=width,
        height=height,
        corner_radius=0.08,
        color=NAVY,
        stroke_width=3,
        fill_color=CREAM,
        fill_opacity=1,
    )
    return _round_outline(box)


def _pointer():
    from manim import Triangle

    tri = Triangle(color=GREEN, stroke_width=0, fill_color=GREEN, fill_opacity=1)
    tri.scale(0.16)
    tri.rotate(-math.pi / 2)
    return tri


def _hand(length: float, degrees: float, width: float):
    from manim import ORIGIN, UP, Line

    hand = Line(ORIGIN, UP * length, color=NAVY, stroke_width=width)
    hand.rotate(-math.radians(degrees), about_point=ORIGIN)
    return hand


def _unit_word(labels) -> str:
    return str(labels.get("unit_word") or "cm")


def _reading(number: int, unit: str) -> str:
    if unit == "cm":
        return f"{number} cm"
    return f"{number}{unit}"


def _length_board(labels, write):
    from manim import VGroup

    a, b = int(labels["a"]), int(labels["b"])
    action = str(labels["action"])
    unit = _unit_word(labels)
    names = labels.get("names")
    if names:
        left_name, right_name = names
    elif action == "ends":
        left_name, right_name = _reading(a, unit), _reading(b, unit)
    else:
        left_name, right_name = "1", "2"
    heights = (0.4, 0.78) if action == "width" else (0.42, 0.42)
    cards = []
    for value, name, height in ((a, left_name, heights[0]), (b, right_name, heights[1])):
        bar = _bar(0.36 * value, height)
        label = write(name, 32)
        label.next_to(bar, DOWN, buff=0.14)
        card = VGroup(bar, label)
        card.vf_bar = bar
        cards.append(card)
    group = VGroup(*cards).arrange(DOWN, buff=0.36)
    target = cards[0].vf_bar.get_left()[0]
    for card in cards[1:]:
        card.shift(RIGHT * (target - card.vf_bar.get_left()[0]))
    if action in {"look", "align"}:
        cards[1].shift(RIGHT * 0.95)
    extras = []
    if action == "match":
        for card in cards:
            dot = _pip(GREEN, 0.1)
            dot.next_to(card.vf_bar, RIGHT, buff=0.1)
            extras.append(dot)
            group.add(dot)
    board = _fresh(group)
    board.vf_bars = [card.vf_bar for card in cards]
    board.vf_later.extend(extras)
    if action == "align":
        board.vf_align = (cards[1], cards[0].vf_bar)
    elif action in {"look", "ends"}:
        marked = cards[0].vf_bar if a >= b else cards[1].vf_bar
        board.vf_strokes.append(marked)
        board.vf_marked = marked
    elif action == "width":
        board.vf_marked = cards[1].vf_bar
        board.vf_strokes.append(cards[1].vf_bar)
    return board


def _distance_board(labels, write):
    from manim import Line, VGroup

    a, b = int(labels["a"]), int(labels["b"])
    action = str(labels["action"])
    unit = _unit_word(labels)
    show_units = bool(labels.get("units"))
    left = -2.2
    top_y, bot_y = 0.72, -0.72
    spine = Line([left, top_y, 0], [left, bot_y, 0], color=NAVY, stroke_width=8)
    _round_outline(spine)
    name = write("S", 36)
    name.next_to(spine, LEFT, buff=0.22)
    lanes = []
    lines = []
    for length, y in ((a, top_y), (b, bot_y)):
        start = [left, y, 0]
        end = [left + 0.46 * length, y, 0]
        line = Line(start, end, color=NAVY, stroke_width=8)
        _round_outline(line)
        pip = _pip(GOLD)
        pip.move_to(end)
        bits = [line, pip]
        if show_units:
            tag = write(_reading(length, unit), 28)
            tag.next_to(pip, RIGHT, buff=0.16)
            bits.append(tag)
        lanes.append(VGroup(*bits))
        lines.append(line)
    group = VGroup(spine, name, *lanes)
    board = _fresh(group)
    board.vf_bars = lines
    if action == "nearer":
        marked = lines[0] if a <= b else lines[1]
        board.vf_strokes.append(marked)
        board.vf_marked = marked
    elif action == "straight":
        board.vf_strokes.extend(lines)
    else:
        longer = 0 if a >= b else 1
        line = lines[longer]
        bend = _bend(line.get_start(), line.get_end(), up=(longer == 0))
        group.add(bend)
        board.vf_later.append(bend)
        board.vf_marked = bend
    return board


def _bend(start, end, up=True):
    from manim import Line, VGroup

    sx, sy, _sz = [float(v) for v in start]
    ex, ey, _ez = [float(v) for v in end]
    lift = 0.7 if up else -0.7
    # Leave the straight gap visible. The detour starts just off that line.
    mid_a = [sx, sy + lift, 0]
    mid_b = [ex, ey + lift, 0]
    path = VGroup(
        Line([sx, sy + (0.08 if up else -0.08), 0], mid_a, color=SIDE, stroke_width=6),
        Line(mid_a, mid_b, color=SIDE, stroke_width=6),
        Line(mid_b, [ex, ey + (0.08 if up else -0.08), 0], color=SIDE, stroke_width=6),
    )
    return path


def _tile_row(count: int, size: str):
    from manim import VGroup

    side = 0.4 if size == "small" else 0.8
    tiles = [_square(side) for _ in range(count)]
    return VGroup(*tiles).arrange(RIGHT, buff=0)


def _units_board(labels, write):
    from manim import Rectangle, VGroup

    action = str(labels["action"])
    if action == "cover":
        count = int(labels["count"])
        tiles = _tile_row(count, str(labels.get("size") or "small"))
        strip = Rectangle(
            width=float(tiles.width) + 0.08,
            height=float(tiles.height) + 0.16,
            color=NAVY,
            stroke_width=4,
            fill_color=CREAM,
            fill_opacity=1,
        )
        _round_outline(strip)
        strip.move_to(tiles)
        number = write(str(count), 36)
        number.next_to(strip, DOWN, buff=0.2)
        group = VGroup(strip, tiles, number)
        board = _fresh(group)
        board.vf_later.extend([tiles, number])
        board.vf_bars = list(tiles)
        return board
    if action == "more":
        low, high = int(labels["low"]), int(labels["high"])
        first = _tile_row(low, "small")
        second = _tile_row(high, "small")
        group = VGroup(first, second).arrange(DOWN, buff=0.32)
        target = first.get_left()[0]
        second.shift(RIGHT * (target - second.get_left()[0]))
        board = _fresh(group)
        longer = second if high >= low else first
        board.vf_strokes.extend(list(longer))
        board.vf_marked = longer
        board.vf_bars = list(first) + list(second)
        return board
    small = _tile_row(6, "small")
    large = _tile_row(3, "large")
    group = VGroup(small, large).arrange(DOWN, buff=0.32)
    large.shift(RIGHT * (small.get_left()[0] - large.get_left()[0]))
    board = _fresh(group)
    board.vf_later.append(large)
    board.vf_bars = list(small) + list(large)
    return board


def _ruler(cm: int, write, numbered: bool):
    from manim import Line, VGroup

    step = 0.46
    left = -cm * step / 2
    base = Line([left, 0, 0], [left + cm * step, 0, 0], color=NAVY, stroke_width=6)
    ticks = []
    labels = []
    for index in range(cm + 1):
        x = left + index * step
        ticks.append(Line([x, -0.14, 0], [x, 0.18, 0], color=NAVY, stroke_width=4))
        if numbered:
            label = write(str(index), 24)
            label.next_to(ticks[-1], DOWN, buff=0.08)
            labels.append(label)
    group = VGroup(base, *ticks, *labels)
    group.vf_left = left
    group.vf_step = step
    return group


def _scale_board(labels, write):
    from manim import Rectangle, VGroup

    action = str(labels["action"])
    unit = _unit_word(labels)
    cm = int(labels.get("cm") or 1)
    if action == "one":
        cm = 1
    ruler = _ruler(cm, write, numbered=True)
    extras = []
    if action == "one":
        block = Rectangle(
            width=ruler.vf_step * 0.72,
            height=0.28,
            color=GREEN,
            stroke_width=0,
            fill_color=GREEN,
            fill_opacity=0.85,
        )
        block.move_to([ruler.vf_left + ruler.vf_step / 2, 0.42, 0])
        caption = write(_reading(1, unit), 32)
        caption.next_to(block, UP, buff=0.12)
        extras.extend([block, caption])
    elif action == "place":
        strip = _bar(ruler.vf_step * cm * 0.92, 0.36)
        strip.move_to([ruler.vf_left + ruler.vf_step * cm / 2, 0.55, 0])
        caption = write(_reading(cm, unit), 32)
        caption.next_to(strip, UP, buff=0.12)
        extras.extend([strip, caption])
    else:
        dots = []
        for index in range(cm):
            dot = _pip(GREEN, 0.1)
            dot.move_to([ruler.vf_left + ruler.vf_step * (index + 0.5), 0.42, 0])
            dots.append(dot)
        caption = write(str(cm), 36)
        caption.next_to(VGroup(*dots), UP, buff=0.12)
        extras.extend(dots + [caption])
    group = VGroup(ruler, *extras)
    board = _fresh(group)
    board.vf_later.extend(extras)
    board.vf_bars = [ruler]
    return board


def _reference_board(labels, write):
    from manim import VGroup

    action = str(labels["action"])
    unit_word = _unit_word(labels)
    if action == "span":
        cm = int(labels.get("cm") or 10)
        bar = _bar(0.28 * cm, 0.46)
        caption = write(_reading(cm, unit_word), 32)
        caption.next_to(bar, DOWN, buff=0.18)
        group = VGroup(bar, caption)
        board = _fresh(group)
        board.vf_later.append(caption)
        board.vf_bars = [bar]
        return board
    unit = int(labels.get("unit") or 2)
    repeats = int(labels.get("repeats") or 3)
    one = _bar(0.4 * unit, 0.4)
    one_label = write(_reading(unit, unit_word), 28)
    one_label.next_to(one, DOWN, buff=0.12)
    sample = VGroup(one, one_label)
    copies = []
    for _ in range(repeats):
        copies.append(_bar(0.4 * unit, 0.4))
    row = VGroup(*copies).arrange(RIGHT, buff=0.08)
    total = write(_reading(unit * repeats, unit_word), 32)
    total.next_to(row, DOWN, buff=0.12)
    copy_group = VGroup(row, total)
    stack = VGroup(sample, copy_group).arrange(DOWN, buff=0.4)
    later = [copy_group]
    if action == "record":
        ruler = _ruler(max(unit * repeats, 1), write, numbered=True)
        ruler.next_to(stack, DOWN, buff=0.35)
        group = VGroup(stack, ruler)
        board = _fresh(group)
        board.vf_later.append(ruler)
        board.vf_bars = [one, *copies]
        return board
    board = _fresh(stack)
    board.vf_later.extend(later)
    board.vf_bars = [one, *copies]
    return board


def _tools_board(labels, write):
    from manim import VGroup

    unit = _unit_word(labels)
    short = _bar(1.35, 0.4)
    long = _bar(4.8, 0.4)
    short_label = write(_reading(15, unit), 28)
    long_label = write(_reading(60, unit), 28)
    short_label.next_to(short, DOWN, buff=0.12)
    long_label.next_to(long, DOWN, buff=0.12)
    top = VGroup(short, short_label)
    bottom = VGroup(long, long_label)
    group = VGroup(top, bottom).arrange(DOWN, buff=0.4)
    bottom.shift(RIGHT * (short.get_left()[0] - long.get_left()[0]))
    board = _fresh(group)
    board.vf_strokes.append(long)
    board.vf_marked = long
    board.vf_bars = [short, long]
    return board


def measure_board(labels, write):
    """The teaching picture. Step-1 pieces sit on ``vf_later`` and ``vf_strokes``."""
    _bind_directions()
    mode = str(labels.get("mode") or "")
    if mode == "length":
        return _length_board(labels, write)
    if mode == "distance":
        return _distance_board(labels, write)
    if mode == "units":
        return _units_board(labels, write)
    if mode == "scale":
        return _scale_board(labels, write)
    if mode == "reference":
        return _reference_board(labels, write)
    return _tools_board(labels, write)


def _coin(cents: int, write):
    from manim import Circle, VGroup

    face = write(coin_face(cents), 30)
    radius = max(0.48, float(face.width) / 2 + 0.16, float(face.height) / 2 + 0.14)
    token = Circle(
        radius=radius,
        color=NAVY,
        stroke_width=5,
        fill_color=GOLD if cents >= 100 else CREAM,
        fill_opacity=1,
    )
    _round_outline(token)
    face.move_to(token)
    group = VGroup(token, face)
    group.vf_coin = token
    return group


def _ring(target):
    from manim import Circle

    ring = Circle(
        radius=max(float(target.width), float(target.height)) / 2 + 0.08,
        color=GREEN,
        stroke_width=6,
    )
    ring.set_fill(opacity=0)
    ring.move_to(target)
    # set_opacity would turn this stroke into a filled disc and hide the coin.
    ring.vf_stroke_only = True
    return ring


def _coin_rows(tokens):
    from manim import VGroup

    per = 4 if len(tokens) > 4 else len(tokens)
    rows = []
    for index in range(0, len(tokens), per):
        rows.append(VGroup(*tokens[index:index + per]).arrange(RIGHT, buff=0.28))
    return VGroup(*rows).arrange(DOWN, buff=0.3)


def coin_board(labels, write):
    _bind_directions()
    from manim import VGroup

    part = str(labels.get("part") or "show")
    coins = [int(value) for value in labels.get("coins") or []]
    if part == "price":
        tags = [_cell(write(price_text(int(value)), 40), GOLD, min_w=2.2, min_h=1.15) for value in labels.get("prices") or []]
        group = VGroup(*tags).arrange(RIGHT, buff=0.4)
        board = _fresh(group)
        board.vf_strokes.append(tags[0].vf_box)
        board.vf_marked = tags[0]
        return board
    if part == "cent":
        token = _coin(coins[0], write)
        word = "cents" if str(labels.get("lang") or "en") == "en" else "分"
        caption = write(f"{coins[0]} {word}" if word == "cents" else f"{coins[0]}{word}", 32)
        caption.next_to(token, DOWN, buff=0.22)
        group = VGroup(token, caption)
        board = _fresh(group)
        board.vf_later.append(caption)
        board.vf_coins = [token]
        return board
    tokens = [_coin(value, write) for value in coins]
    if part == "swap":
        other = [_coin(value, write) for value in labels.get("into") or []]
        left = _coin_rows(tokens)
        right = _coin_rows(other)
        arrow = _pointer()
        group = VGroup(left, arrow, right).arrange(RIGHT, buff=0.28)
        board = _fresh(group)
        board.vf_later.extend([arrow, right])
        board.vf_coins = tokens + other
        return board
    row = _coin_rows(tokens)
    if part == "total":
        total = sum(coins)
        tag = _cell(write(price_text(total), 36), GOLD, min_w=1.8, min_h=0.9)
        tag.next_to(row, DOWN, buff=0.28)
        group = VGroup(row, tag)
        board = _fresh(group)
        board.vf_later.append(tag)
        board.vf_coins = tokens
        return board
    focus = int(labels.get("focus") or 0)
    ring = _ring(tokens[focus].vf_coin)
    group = VGroup(row, ring)
    board = _fresh(group)
    board.vf_later.append(ring)
    board.vf_ring = ring
    board.vf_coins = tokens
    return board


def _clock(hour: int, minute: int, write, radius: float = 1.7):
    from manim import Circle, Line, VGroup

    face = Circle(
        radius=radius,
        color=NAVY,
        stroke_width=6,
        fill_color=CREAM,
        fill_opacity=1,
    )
    _round_outline(face)
    ticks = []
    numbers = []
    for number in range(1, 13):
        angle = math.pi / 2 - number * (2 * math.pi / 12)
        outer = radius * 0.92
        inner = radius * 0.82
        ticks.append(Line(
            [inner * math.cos(angle), inner * math.sin(angle), 0],
            [outer * math.cos(angle), outer * math.sin(angle), 0],
            color=NAVY,
            stroke_width=3,
        ))
        spot = radius * 0.64
        label = write(str(number), 22)
        label.move_to([spot * math.cos(angle), spot * math.sin(angle), 0])
        numbers.append(label)
    minute_deg = minute / 60.0 * 360.0
    hour_deg = (hour % 12) * 30.0 + minute * 0.5
    minute_hand = _hand(radius * 0.72, minute_deg, 5)
    hour_hand = _hand(radius * 0.46, hour_deg, 8)
    centre = _pip(NAVY, 0.07)
    group = VGroup(face, *ticks, *numbers, minute_hand, hour_hand, centre)
    group.vf_face = face
    group.vf_hour = hour_hand
    group.vf_minute = minute_hand
    return group


def _hour_list(start: int, steps: int) -> list[int]:
    return [((start - 1 + index) % 12) + 1 for index in range(steps + 1)]


def _hop_text(hour: int, minute: int) -> str:
    if minute:
        return f"{hour}:{minute:02d}"
    return str(hour)


def day_board(labels, write):
    _bind_directions()
    from manim import VGroup

    mode = str(labels.get("mode") or "clock")
    lang = str(labels.get("lang") or "en")
    if mode == "clock":
        clock = _clock(int(labels["hour"]), int(labels["minute"]), write)
        board = _fresh(clock)
        hand = clock.vf_hour if str(labels.get("hand") or "hour") == "hour" else clock.vf_minute
        board.vf_strokes.append(hand)
        board.vf_marked = hand
        board.vf_hour = clock.vf_hour
        board.vf_minute = clock.vf_minute
        board.vf_face = clock.vf_face
        return board
    if mode == "hops":
        minute = int(labels.get("minute") or 0)
        hours = _hour_list(int(labels["start"]), int(labels["steps"]))
        pieces = []
        later = []
        for index, hour in enumerate(hours):
            cell = _cell(write(_hop_text(hour, minute), 30), GOLD if index == len(hours) - 1 else CREAM)
            if index == 0:
                pieces.append(cell)
            else:
                arrow = _pointer()
                pieces.extend([arrow, cell])
                later.extend([arrow, cell])
        group = VGroup(*pieces).arrange(RIGHT, buff=0.14)
        board = _fresh(group)
        board.vf_later.extend(later)
        return board
    if mode == "week":
        names = list(labels.get("days") or WEEKDAYS[lang])
        cells = [_cell(write(name, 26), CREAM, min_w=0.78, min_h=0.7) for name in names]
        group = VGroup(*cells).arrange(RIGHT, buff=0.1)
        board = _fresh(group)
        board.vf_strokes.extend([cells[0].vf_box, cells[-1].vf_box])
        board.vf_marked = cells[-1]
        return board
    if mode == "months":
        cells = [_cell(write(str(number), 26), CREAM, min_w=0.62, min_h=0.58) for number in range(1, 13)]
        top = VGroup(*cells[:6]).arrange(RIGHT, buff=0.1)
        bottom = VGroup(*cells[6:]).arrange(RIGHT, buff=0.1)
        grid = VGroup(top, bottom).arrange(DOWN, buff=0.14)
        badge = _cell(write("12", 34), GOLD, min_w=0.8, min_h=0.7)
        badge.next_to(grid, DOWN, buff=0.24)
        group = VGroup(grid, badge)
        board = _fresh(group)
        board.vf_later.append(badge)
        return board
    year = int(labels.get("year") or 2026)
    month = int(labels.get("month") or 11)
    day = int(labels.get("day") or 18)
    names = list(labels.get("days") or WEEKDAYS[lang])
    probe = write("30", 22)
    cell_w = max(0.5, float(probe.width) + 0.22)
    cell_h = max(0.44, float(probe.height) + 0.16)
    heads = []
    for name in names:
        label = write(name, 20)
        if float(label.width) > cell_w - 0.08:
            label.scale((cell_w - 0.08) / float(label.width))
        box = _blank_cell(cell_w, cell_h)
        label.move_to(box)
        heads.append(VGroup(box, label))
    header = VGroup(*heads).arrange(RIGHT, buff=0.06)
    weeks = calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
    rows = []
    marked = None
    for week in weeks:
        row_cells = []
        for number in week:
            if number == 0:
                row_cells.append(_blank_cell(cell_w, cell_h))
                continue
            label = write(str(number), 22)
            box = _blank_cell(cell_w, cell_h)
            label.move_to(box)
            cell = VGroup(box, label)
            row_cells.append(cell)
            if number == day:
                marked = box
        rows.append(VGroup(*row_cells).arrange(RIGHT, buff=0.06))
    grid = VGroup(*rows).arrange(DOWN, buff=0.06)
    heading = write(str(labels.get("month_name") or ""), 28)
    body = VGroup(header, grid).arrange(DOWN, buff=0.12)
    # arrange centres a short last week. Put every column back under its heading.
    for row in rows:
        row.shift(RIGHT * (header.get_left()[0] - row.get_left()[0]))
    if str(labels.get("month_name") or "").strip():
        group = VGroup(heading, body).arrange(DOWN, buff=0.16)
    else:
        group = body
    board = _fresh(group)
    if marked is not None:
        board.vf_strokes.append(marked)
        board.vf_marked = marked
    board.vf_day = day
    board.vf_column = calendar.weekday(year, month, day)
    return board


def everyday_icon(picture, write, lang: str = "en"):
    """A small cue or hook picture. It stays readable beside one sentence."""
    _bind_directions()
    from manim import VGroup

    kind = picture[0]
    if kind == "measure":
        mode = picture[1]
        if mode == "length":
            first = _bar(0.28 * int(picture[2]), 0.32)
            second = _bar(0.28 * int(picture[3]), 0.32)
            group = VGroup(first, second).arrange(DOWN, buff=0.18)
            second.shift(RIGHT * (first.get_left()[0] - second.get_left()[0]))
            return group
        if mode == "distance":
            return _distance_board({"a": picture[2], "b": picture[3], "action": "straight", "units": False}, write)
        if mode == "units":
            return _tile_row(min(int(picture[2]), 6), "small")
        ruler = _ruler(int(picture[2]), write, numbered=True)
        return ruler
    if kind == "coin":
        if picture[1] == "price":
            return _cell(write(price_text(int(picture[2])), 32), GOLD, min_w=1.6, min_h=0.85)
        if picture[1] == "swap":
            left = VGroup(*[_coin(int(value), write) for value in picture[2]]).arrange(RIGHT, buff=0.08)
            right = VGroup(*[_coin(int(value), write) for value in picture[3]]).arrange(RIGHT, buff=0.08)
            return VGroup(left, _pointer(), right).arrange(RIGHT, buff=0.12)
        if picture[1] == "row":
            return VGroup(*[_coin(int(value), write) for value in picture[2]]).arrange(RIGHT, buff=0.08)
        return _coin(int(picture[1]), write)
    if picture[1] == "clock":
        return _clock(int(picture[2]), int(picture[3]), write, radius=1.15)
    if picture[1] == "hops":
        minute = int(picture[4]) if len(picture) > 4 else 0
        hours = _hour_list(int(picture[2]), int(picture[3]))
        bits = []
        for index, hour in enumerate(hours):
            if index:
                bits.append(_pointer())
            bits.append(_cell(write(_hop_text(hour, minute), 24), CREAM, min_w=0.7, min_h=0.55))
        return VGroup(*bits).arrange(RIGHT, buff=0.08)
    if picture[1] == "week":
        names = WEEKDAYS.get(lang, WEEKDAYS["en"])
        cells = [_cell(write(name, 20), CREAM, min_w=0.55, min_h=0.48) for name in names]
        return VGroup(*cells).arrange(RIGHT, buff=0.06)
    if picture[1] == "months":
        cells = [_cell(write(str(number), 20), CREAM, min_w=0.42, min_h=0.4) for number in range(1, 13)]
        return VGroup(
            VGroup(*cells[:6]).arrange(RIGHT, buff=0.05),
            VGroup(*cells[6:]).arrange(RIGHT, buff=0.05),
        ).arrange(DOWN, buff=0.08)
    return _cell(write(str(picture[2]), 36), GOLD, min_w=0.9, min_h=0.8)
