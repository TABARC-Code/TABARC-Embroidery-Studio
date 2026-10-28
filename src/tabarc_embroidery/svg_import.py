"""Deliberately restricted, safe SVG subset. Unsupported geometry fails loudly.

No external entities, CSS layout, references, arc commands or text: this is a
physical-scale import prototype, not a full SVG renderer.
"""
from __future__ import annotations

import hashlib
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from .model import Document, Point, Stroke

_NUMBER = r"[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?"
_TOKENS = re.compile(rf"[a-zA-Z]|{_NUMBER}")
_TRANSFORM = re.compile(r"([a-zA-Z]+)\s*\(([^)]*)\)")
_LENGTH = re.compile(rf"^\s*({_NUMBER})\s*(mm|cm|in|pt|px)?\s*$")
_MM_PER_PX = 25.4 / 96
_MAX_BYTES = 5_000_000
_MAX_ELEMENTS = 20_000
_MAX_PATH_TOKENS = 100_000


@dataclass(frozen=True)
class Matrix:
    a: float = 1
    b: float = 0
    c: float = 0
    d: float = 1
    e: float = 0
    f: float = 0

    def __matmul__(self, other: "Matrix") -> "Matrix":
        return Matrix(
            self.a * other.a + self.c * other.b,
            self.b * other.a + self.d * other.b,
            self.a * other.c + self.c * other.d,
            self.b * other.c + self.d * other.d,
            self.a * other.e + self.c * other.f + self.e,
            self.b * other.e + self.d * other.f + self.f,
        )

    def apply(self, p: Point) -> Point:
        return Point(self.a * p.x + self.c * p.y + self.e,
                     self.b * p.x + self.d * p.y + self.f)


def _numbers(s: str) -> list[float]:
    # Accept comma/space separators and minus signs without a separator.
    tokens = list(_TOKENS.finditer(s))
    if re.sub(r"[,\s]", "", _TOKENS.sub("", s)):
        raise ValueError(f"Invalid numeric expression {s!r}")
    return [float(m.group()) for m in tokens]


def _transform(source: str | None) -> Matrix:
    if not source:
        return Matrix()
    m = Matrix()
    i = 0
    for match in _TRANSFORM.finditer(source):
        if source[i:match.start()].strip(" ,\t\n\r"):
            raise ValueError("Malformed SVG transform")
        i = match.end()
        name, raw = match.groups()
        v = _numbers(raw)
        if name == "matrix" and len(v) == 6:
            op = Matrix(*v)
        elif name == "translate" and len(v) in (1, 2):
            op = Matrix(e=v[0], f=v[1] if len(v) == 2 else 0)
        elif name == "scale" and len(v) in (1, 2):
            op = Matrix(a=v[0], d=v[1] if len(v) == 2 else v[0])
        elif name == "rotate" and len(v) in (1, 3):
            rad = math.radians(v[0])
            rotate = Matrix(a=math.cos(rad), b=math.sin(rad),
                            c=-math.sin(rad), d=math.cos(rad))
            if len(v) == 3:
                op = Matrix(e=v[1], f=v[2]) @ rotate @ Matrix(e=-v[1], f=-v[2])
            else:
                op = rotate
        elif name in ("skewX", "skewY") and len(v) == 1:
            tangent = math.tan(math.radians(v[0]))
            op = Matrix(c=tangent) if name == "skewX" else Matrix(b=tangent)
        else:
            raise ValueError(f"Unsupported SVG transform: {name} {v}")
        # SVG transform lists are applied in declared sequence, rightmost first.
        m = m @ op
    if source[i:].strip(" ,\t\n\r"):
        raise ValueError("Malformed SVG transform suffix")
    return m


def _mm(value: str) -> float:
    m = _LENGTH.fullmatch(value)
    if not m:
        raise ValueError(f"Unsupported SVG length {value!r}")
    number, unit = m.groups()
    conversions = {"mm": 1, "cm": 10, "in": 25.4, "pt": 25.4 / 72,
                   "px": _MM_PER_PX, None: _MM_PER_PX}
    return float(number) * conversions[unit]


def _unitless(element: ET.Element, attribute: str, default: str = "0") -> float:
    s = element.get(attribute, default).strip()
    if not re.fullmatch(_NUMBER, s):
        raise ValueError(f"{attribute} must be unitless in this SVG subset: {s!r}")
    return float(s)


def _dist_line(p: Point, a: Point, b: Point) -> float:
    dx, dy = b.x - a.x, b.y - a.y
    if dx == 0 and dy == 0:
        return math.hypot(p.x - a.x, p.y - a.y)
    return abs(dy * p.x - dx * p.y + b.x * a.y - b.y * a.x) / math.hypot(dx, dy)


def _cubic(a: Point, b: Point, c: Point, d: Point, mm_matrix: Matrix,
           tolerance: float, depth: int = 0) -> list[Point]:
    # Work in final physical coordinates: shear/scale can alter flattening error.
    ta, tb, tc, td = (mm_matrix.apply(p) for p in (a, b, c, d))
    if max(_dist_line(tb, ta, td), _dist_line(tc, ta, td)) <= tolerance:
        return [td]
    if depth >= 12:
        raise ValueError("Bezier flattening exceeded safety recursion limit")
    ab = _mid(a, b)
    bc = _mid(b, c)
    cd = _mid(c, d)
    abc, bcd = _mid(ab, bc), _mid(bc, cd)
    halfway = _mid(abc, bcd)
    return (_cubic(a, ab, abc, halfway, mm_matrix, tolerance, depth + 1)
            + _cubic(halfway, bcd, cd, d, mm_matrix, tolerance, depth + 1))


def _mid(a: Point, b: Point) -> Point:
    return Point((a.x + b.x) / 2, (a.y + b.y) / 2)


def _path(d: str, matrix: Matrix, tolerance: float, name: str) -> list[Stroke]:
    matches = list(_TOKENS.finditer(d))
    if len(matches) > _MAX_PATH_TOKENS:
        raise ValueError("SVG path token limit exceeded")
    for i, m in enumerate(matches):
        if d[(matches[i - 1].end() if i else 0):m.start()].strip(" ,\t\r\n"):
            raise ValueError("Malformed SVG path syntax")
    if d[(matches[-1].end() if matches else 0):].strip(" ,\t\r\n"):
        raise ValueError("Malformed SVG path suffix")
    t = [m.group() for m in matches]
    i, command = 0, ""
    curr = Point(0, 0)
    start = Point(0, 0)
    points: list[Point] = []
    result: list[Stroke] = []
    last_cubic: Point | None = None
    last_quad: Point | None = None
    last_type = ""

    def finish(closed: bool = False) -> None:
        if points:
            if len(points) < 2:
                raise ValueError(f"Degenerate path {name!r}")
            result.append(Stroke(f"{name}:{len(result)+1}", tuple(points), closed))
            points.clear()

    def read(count: int) -> list[float]:
        nonlocal i
        if i + count > len(t) or any(v.isalpha() for v in t[i:i + count]):
            raise ValueError("Missing path coordinate")
        out = [float(v) for v in t[i:i + count]]
        i += count
        return out

    while i < len(t):
        if t[i].isalpha():
            command = t[i]
            i += 1
        if not command:
            raise ValueError("SVG path must begin with a command")
        relative = command.islower()
        cmd = command.upper()
        if cmd == "A":
            raise ValueError("Elliptical arc (A/a) is not supported yet")
        if cmd == "Z":
            if points:
                finish(True)
            curr = start
            last_cubic = last_quad = None
            last_type = cmd
            command = ""  # avoid a malformed trailing coordinate looping forever
            continue
        if cmd not in "MLHVCSQT":
            raise ValueError(f"Unsupported SVG path command: {command}")
        nums = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4,
                "Q": 4, "T": 2}[cmd]
        raw = read(nums)

        def p(x: float, y: float) -> Point:
            return Point(curr.x + x, curr.y + y) if relative else Point(x, y)

        if cmd == "M":
            finish()
            curr = p(*raw)
            start = curr
            points.append(matrix.apply(curr))
            command = "l" if relative else "L"
        elif cmd in "LHV":
            dest = p(*raw) if cmd == "L" else p(raw[0], 0) if cmd == "H" and relative else (
                Point(raw[0], curr.y) if cmd == "H" else p(0, raw[0]) if relative else Point(curr.x, raw[0]))
            curr = dest
            points.append(matrix.apply(curr))
        elif cmd in "CS":
            if cmd == "C":
                c1, c2, dest = p(raw[0], raw[1]), p(raw[2], raw[3]), p(raw[4], raw[5])
            else:
                c1 = Point(2 * curr.x - last_cubic.x, 2 * curr.y - last_cubic.y) if (
                    last_type in ("C", "S") and last_cubic) else curr
                c2, dest = p(raw[0], raw[1]), p(raw[2], raw[3])
            points.extend(_cubic(curr, c1, c2, dest, matrix, tolerance))
            curr, last_cubic = dest, c2
        else:
            if cmd == "Q":
                control, dest = p(raw[0], raw[1]), p(raw[2], raw[3])
            else:
                control = Point(2 * curr.x - last_quad.x, 2 * curr.y - last_quad.y) if (
                    last_type in ("Q", "T") and last_quad) else curr
                dest = p(*raw)
            c1 = Point(curr.x + (control.x - curr.x) * 2 / 3,
                       curr.y + (control.y - curr.y) * 2 / 3)
            c2 = Point(dest.x + (control.x - dest.x) * 2 / 3,
                       dest.y + (control.y - dest.y) * 2 / 3)
            points.extend(_cubic(curr, c1, c2, dest, matrix, tolerance))
            curr, last_quad = dest, control
        if len(points) > 100_000:
            raise ValueError("Path flattening point limit exceeded")
        if cmd not in "CS":
            last_cubic = None
        if cmd not in "QT":
            last_quad = None
        last_type = cmd
    finish()
    return result


def import_svg(data: bytes, tolerance_mm: float = 0.06) -> Document:
    if len(data) > _MAX_BYTES:
        raise ValueError("SVG exceeds 5 MB safety limit")
    if not 0.005 <= tolerance_mm <= 1:
        raise ValueError("SVG flattening tolerance must be 0.005 to 1 mm")
    if re.search(rb"<!\s*(?:DOCTYPE|ENTITY)\b", data, re.I):
        raise ValueError("SVG DTD and XML entities are not permitted")
    root = ET.fromstring(data)
    if root.tag.split("}")[-1] != "svg":
        raise ValueError("Expected an SVG root element")
    viewbox = root.get("viewBox")
    box = _numbers(viewbox) if viewbox else None
    if box is not None and (len(box) != 4 or box[2] <= 0 or box[3] <= 0):
        raise ValueError("Invalid SVG viewBox")
    if root.get("width") is None and box is None:
        raise ValueError("SVG requires width/height or a viewBox")
    if root.get("height") is None and box is None:
        raise ValueError("SVG requires height or a viewBox")
    width_mm = _mm(root.get("width") if root.get("width") is not None else f"{box[2]}px")
    height_mm = _mm(root.get("height") if root.get("height") is not None else f"{box[3]}px")
    if not 0 < width_mm <= 2000 or not 0 < height_mm <= 2000:
        raise ValueError("SVG dimensions outside safe import range")
    if box:
        x, y, w, h = box
        sx, sy = width_mm / w, height_mm / h
        preserve = root.get("preserveAspectRatio", "xMidYMid meet").strip()
        if preserve == "none":
            matrix = Matrix(sx, 0, 0, sy, -x * sx, -y * sy)
        else:
            parts = preserve.split()
            if parts[-1] == "slice" or parts[0] not in (
                "xMinYMin", "xMidYMin", "xMaxYMin", "xMinYMid", "xMidYMid",
                "xMaxYMid", "xMinYMax", "xMidYMax", "xMaxYMax"):
                raise ValueError(f"Unsupported preserveAspectRatio: {preserve}")
            s = min(sx, sy)
            align = parts[0]
            ax = 0 if "xMin" in align else (width_mm - w * s) if "xMax" in align else (width_mm - w * s) / 2
            ay = 0 if "YMin" in align else (height_mm - h * s) if "YMax" in align else (height_mm - h * s) / 2
            matrix = Matrix(s, 0, 0, s, ax - x * s, ay - y * s)
    else:
        matrix = Matrix(_MM_PER_PX, 0, 0, _MM_PER_PX)
    if root.get("transform"):
        raise ValueError("Root-level SVG transforms are not supported yet")
    strokes: list[Stroke] = []
    counter = 0

    def visit(element: ET.Element, parent: Matrix) -> None:
        nonlocal counter
        counter += 1
        if counter > _MAX_ELEMENTS:
            raise ValueError("SVG element limit exceeded")
        tag = element.tag.split("}")[-1]
        if element.get("display") == "none" or element.get("visibility") == "hidden":
            return
        style = element.get("style", "")
        if re.search(r"(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden)(?:\s*;|\s*$)", style):
            return
        mx = parent @ _transform(element.get("transform"))
        name = element.get("id", f"{tag}-{counter}")
        if tag in ("svg", "g"):
            if element is not root and tag == "svg":
                raise ValueError("Nested SVG viewports are not supported yet")
            for child in element:
                visit(child, mx)
        elif tag == "path":
            strokes.extend(_path(element.get("d", ""), mx, tolerance_mm, name))
        elif tag == "line":
            a = mx.apply(Point(_unitless(element, "x1"), _unitless(element, "y1")))
            b = mx.apply(Point(_unitless(element, "x2"), _unitless(element, "y2")))
            if a != b:
                strokes.append(Stroke(name, (a, b)))
        elif tag in ("polyline", "polygon"):
            coords = _numbers(element.get("points", ""))
            if len(coords) < 4 or len(coords) % 2:
                raise ValueError(f"Invalid {tag} coordinates")
            pts = tuple(mx.apply(Point(coords[k], coords[k + 1])) for k in range(0, len(coords), 2))
            strokes.append(Stroke(name, pts, tag == "polygon"))
        elif tag == "rect":
            if element.get("rx") or element.get("ry"):
                raise ValueError("Rounded rectangles not supported yet")
            x, y = _unitless(element, "x"), _unitless(element, "y")
            w, h = _unitless(element, "width"), _unitless(element, "height")
            if w <= 0 or h <= 0:
                raise ValueError("Rectangle dimensions must be positive")
            pts = tuple(mx.apply(Point(a, b)) for a, b in (
                (x, y), (x + w, y), (x + w, y + h), (x, y + h)))
            strokes.append(Stroke(name, pts, True))
        elif tag in ("defs", "metadata", "title", "desc", "style"):
            return
        elif tag in ("image", "text", "circle", "ellipse", "use", "symbol", "foreignObject"):
            raise ValueError(f"Unsupported SVG element <{tag}>; convert it to paths first")
        else:
            raise ValueError(f"Unknown SVG element <{tag}>; refusing partial import")

    visit(root, matrix)
    if not strokes:
        raise ValueError("No usable paths in SVG")
    if sum(len(s.points) for s in strokes) > 500_000:
        raise ValueError("SVG total geometry point limit exceeded")
    return Document(width_mm, height_mm, tuple(strokes), hashlib.sha256(data).hexdigest())
