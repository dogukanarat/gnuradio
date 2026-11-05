from PyQt6.QtGui import QPainterPath, QPainterPathStroker, QPainter, QPen, QBrush, QPolygonF
from PyQt6.QtWidgets import QGraphicsPathItem, QApplication
from PyQt6.QtCore import QPointF, Qt

from enum import Enum

from ....core.Connection import Connection as CoreConnection
from . import colors
from ...Constants import (
    CONNECTOR_ARROW_BASE,
    CONNECTOR_ARROW_HEIGHT,
    CONNECTOR_EXTENSION_MINIMAL,
)

# Radius of the dot drawn where connections from one output branch off
BRANCH_DOT_RADIUS = 2.8
# Distance kept below the lower block when routing a feedback connection
FEEDBACK_CLEARANCE = 18.0


def _unit(vector):
    """Snap a direction vector to the nearest axis (blocks rotate in 90 degree steps)."""
    if abs(vector.x()) >= abs(vector.y()):
        return QPointF(1.0 if vector.x() >= 0 else -1.0, 0.0)
    return QPointF(0.0, 1.0 if vector.y() >= 0 else -1.0)


def _arrowhead(tip, direction):
    """Filled triangle with its tip at `tip`, pointing along `direction`."""
    d = _unit(direction)
    normal = QPointF(-d.y(), d.x())
    base = tip - d * CONNECTOR_ARROW_HEIGHT
    half = CONNECTOR_ARROW_BASE / 2.0
    path = QPainterPath()
    path.addPolygon(QPolygonF([tip, base + normal * half, base - normal * half, tip]))
    path.closeSubpath()
    return path


def _elbow(path, p1, p2, horizontal_first):
    """Connect p1 to p2 with a Z shaped path, bending half way."""
    if horizontal_first:
        mid_x = (p1.x() + p2.x()) / 2.0
        path.lineTo(QPointF(mid_x, p1.y()))
        path.lineTo(QPointF(mid_x, p2.y()))
    else:
        mid_y = (p1.y() + p2.y()) / 2.0
        path.lineTo(QPointF(p1.x(), mid_y))
        path.lineTo(QPointF(p2.x(), mid_y))
    path.lineTo(p2)


class StyledConnection():
    """
    Styled connection; current styles:
    - CURVED: cubic spline
    - ANGLED: orthogonal connection (horizontal and vertical segments only)
    """
    class ConnectionStyle(Enum):
        CURVED = 0
        ANGLED = 1

    def __init__(self):
        self._qsettings = QApplication.instance().qsettings
        self._conn_style_str = self._qsettings.value("appearance/connection_style", "ANGLED", type=str)
        try:
            self._conn_style = self.ConnectionStyle[self._conn_style_str]
        except KeyError:
            self._conn_style = self.ConnectionStyle.ANGLED
        self._line_width_factor = self._qsettings.value("appearance/line_width_factor", 1.0, type=float)


class DummyConnection(QGraphicsPathItem, StyledConnection):
    """
    Dummy connection used for when the user drags a connection
    between two ports.
    """

    def __init__(self, parent, start_point, end_point):
        super(DummyConnection, self).__init__()
        super(StyledConnection, self).__init__()

        self.start_point = start_point
        self.end_point = end_point

        self._line = QPainterPath()
        self._arrowhead = QPainterPath()
        self._path = QPainterPath()
        self.update(end_point)

        self._color1 = self._color2 = None

        self._current_port_rotations = self._current_coordinates = None

        self._rel_points = None  # connection coordinates relative to sink/source
        self._arrow_rotation = 0.0  # rotation of the arrow in radians
        self._current_cr = None  # for what_is_selected() of curved line
        self._line_path = None
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable)

    def update(self, end_point):
        """User moved the mouse, redraw with new end point"""
        self.end_point = end_point
        line_end = self.end_point - QPointF(CONNECTOR_ARROW_HEIGHT, 0)
        self._line.clear()
        self._line.moveTo(self.start_point)
        if self._conn_style == StyledConnection.ConnectionStyle.CURVED:
            c1 = self.start_point + QPointF(200, 0)
            c2 = line_end - QPointF(200, 0)
            self._line.cubicTo(c1, c2, line_end)
        else:
            _elbow(self._line, self.start_point, line_end, horizontal_first=True)

        self._arrowhead = _arrowhead(self.end_point, QPointF(1.0, 0.0))

        self._path.clear()
        self._path.addPath(self._line)
        self._path.addPath(self._arrowhead)
        self.setPath(self._path)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        color = colors.HIGHLIGHT_COLOR

        pen = QPen(color)
        pen.setWidthF(1.6 * self._line_width_factor)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._line)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPath(self._arrowhead)


class Connection(CoreConnection):
    def __init__(self, parent, source, sink):
        super(Connection, self).__init__(parent, source, sink)
        self.gui = GUIConnection(self, parent, source, sink)


class GUIConnection(QGraphicsPathItem, StyledConnection):
    def __init__(self, core, parent, source, sink):
        super(StyledConnection, self).__init__()
        self.core = core
        super(QGraphicsPathItem, self).__init__()

        self.source = source
        self.sink = sink

        self._line = QPainterPath()
        self._arrowhead = QPainterPath()
        self._branch_dot = QPainterPath()
        self._path = QPainterPath()

        self._color1 = self._color2 = None

        self._current_port_rotations = self._current_coordinates = None

        self._rel_points = None  # connection coordinates relative to sink/source
        self._arrow_rotation = 0.0  # rotation of the arrow in radians
        self._current_cr = None  # for what_is_selected() of curved line
        self._line_path = None
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable)
        self.update()

    # ------------------------------------------------------------- routing
    def _sinks_of_source(self):
        """(end point, direction, sink block) of every connection leaving our source port."""
        result = []
        for conn in self.source.connections():
            gui = getattr(conn, "gui", None)
            sink = gui.sink if gui is not None else conn.sink_port
            try:
                result.append((sink.gui.connection_point, _unit(sink.gui.direction), sink.parent_block))
            except Exception:
                continue
        return result

    def _obstacles(self, skip=()):
        """Scene rectangles of the blocks a line should not run through."""
        rects = []
        skip = set(skip) | {self.source.parent_block, self.sink.parent_block}
        try:
            blocks = self.core.parent.blocks
        except AttributeError:
            return rects
        for block in blocks:
            if block in skip:
                continue
            gui = getattr(block, "gui", None)
            if gui is None or not gui.isVisible():
                continue
            if getattr(gui, "hide_variables", False) and (block.is_variable or block.is_import):
                continue
            # the bounding rect already includes a small margin around the block
            rects.append(gui.sceneBoundingRect())
        return rects

    @staticmethod
    def _hits(points, obstacles):
        """True if the polyline through `points` crosses any obstacle."""
        for a, b in zip(points, points[1:]):
            if abs(a.y() - b.y()) < 0.01:      # horizontal segment
                y = a.y()
                x1, x2 = sorted((a.x(), b.x()))
                for r in obstacles:
                    if r.top() < y < r.bottom() and x1 < r.right() and x2 > r.left():
                        return True
            else:                              # vertical segment
                x = a.x()
                y1, y2 = sorted((a.y(), b.y()))
                for r in obstacles:
                    if r.left() < x < r.right() and y1 < r.bottom() and y2 > r.top():
                        return True
        return False

    @staticmethod
    def _candidates(preferred, low, high, step=8.0):
        """`preferred` first, then positions in [low, high] moving away from it."""
        yield preferred
        k = 1
        while preferred - k * step >= low or preferred + k * step <= high:
            for value in (preferred + k * step, preferred - k * step):
                if low <= value <= high:
                    yield value
            k += 1

    def _channel(self, x1, x2, y, obstacles, downwards):
        """Move the horizontal run y (between x1 and x2) off any block in the way."""
        for _ in range(len(obstacles) + 1):
            left, right = sorted((x1, x2))
            blocking = [r for r in obstacles
                        if r.top() <= y <= r.bottom() and left < r.right() and right > r.left()]
            if not blocking:
                return y
            if downwards:
                y = max(r.bottom() for r in blocking) + FEEDBACK_CLEARANCE / 2
            else:
                y = min(r.top() for r in blocking) - FEEDBACK_CLEARANCE / 2
        return y

    def _nearest_channel(self, x1, x2, y, obstacles):
        below = self._channel(x1, x2, y, obstacles, downwards=True)
        above = self._channel(x1, x2, y, obstacles, downwards=False)
        return below if abs(below - y) <= abs(above - y) else above

    def _route_forward(self, start, end):
        """
        Left-to-right connection, routed like a Simulink signal line:
        horizontal out of the source, one vertical run, horizontal into the
        sink. Lines leaving one output share that vertical run (the trunk) and
        branch off it at a dot. Blocks in the way are avoided.
        """
        right = QPointF(1.0, 0.0)
        group = [(e, blk) for e, d, blk in self._sinks_of_source() if d == right and e.x() >= start.x()]
        if not any(blk is self.sink.parent_block and abs(e.x() - end.x()) < 0.01 and abs(e.y() - end.y()) < 0.01
                   for e, blk in group):
            group.append((end, self.sink.parent_block))
        branched = len(group) > 1
        # The trunk must be the same for every line of the group, so all of
        # them use the same obstacles: everything but the source and the sinks.
        obstacles = self._obstacles(skip=[blk for _, blk in group])
        ends = [e for e, _ in group]

        # A nearly straight line is drawn straight (no 1-2 px jog), as long as
        # the line starts on the block border and does not branch.
        if not branched and abs(end.y() - start.y()) < 5 and not self.source.gui._draws_body():
            straight = [QPointF(start.x(), end.y()), end]
            if not self._hits(straight, obstacles):
                self._line.clear()
                self._line.moveTo(straight[0])
                self._line.lineTo(end)
                return

        nearest = min(e.x() for e in ends)
        low = start.x() + 4.0
        high = max(low, nearest - 4.0)
        preferred = start.x() + (nearest - start.x()) / 2.0

        def simple(x, e):
            return [QPointF(x, start.y()), QPointF(x, e.y()), e]

        # Pick the trunk position: its stub out of the source must be clear;
        # prefer one from which every branch runs straight to its sink.
        trunk, best = None, -1
        for x in self._candidates(preferred, low, high):
            if self._hits([start, QPointF(x, start.y())], obstacles):
                continue
            clear = sum(not self._hits(simple(x, e), obstacles) for e in ends)
            if clear > best:
                trunk, best = x, clear
            if clear == len(ends):
                break
        if trunk is None:
            trunk = preferred

        tee = QPointF(trunk, start.y())
        self._line.lineTo(tee)
        if branched:
            self._branch_dot.addEllipse(tee, BRANCH_DOT_RADIUS, BRANCH_DOT_RADIUS)
        if not self._hits(simple(trunk, end), obstacles):
            for p in simple(trunk, end)[1:]:
                self._line.lineTo(p)
            return

        # This branch has blocks in its way: drop to a free horizontal
        # channel, run along it and come back up to the input.
        x2 = max(trunk, end.x() - CONNECTOR_EXTENSION_MINIMAL)
        y = self._nearest_channel(trunk, x2, end.y(), obstacles)
        for p in (QPointF(trunk, y), QPointF(x2, y), QPointF(x2, end.y()), end):
            self._line.lineTo(p)

    def _route_feedback(self, start, end, ds, dk):
        """
        Right-to-left connection (a feedback path): leave the output, run back
        through the gap between the two blocks, or below both when they
        overlap vertically, and enter the input from the left.
        """
        ext = CONNECTOR_EXTENSION_MINIMAL
        obstacles = self._obstacles()
        p1 = start + ds * ext
        p2 = end - dk * ext
        src = self.source.parent_block.gui.sceneBoundingRect()
        snk = self.sink.parent_block.gui.sceneBoundingRect()
        blocks = obstacles + [src, snk]
        # Preferred channel: the gap between the blocks, then below both, then above both
        wanted = []
        if snk.top() > src.bottom():
            wanted.append(((src.bottom() + snk.top()) / 2.0, None))
        elif snk.bottom() < src.top():
            wanted.append(((snk.bottom() + src.top()) / 2.0, None))
        wanted.append((max(src.bottom(), snk.bottom()) + FEEDBACK_CLEARANCE / 2, True))
        wanted.append((min(src.top(), snk.top()) - FEEDBACK_CLEARANCE / 2, False))

        def path(y):
            return [p1, QPointF(p1.x(), y), QPointF(p2.x(), y), p2, end]

        routes = []
        for y, downwards in wanted:
            if downwards is None:
                y = self._nearest_channel(p1.x(), p2.x(), y, blocks)
            else:
                y = self._channel(p1.x(), p2.x(), y, blocks, downwards)
            routes.append(path(y))
        # the stubs at both ends belong to the source and sink blocks
        chosen = next((r for r in routes if not self._hits(r[1:-1], obstacles)), routes[0])
        for p in chosen:
            self._line.lineTo(p)
        # Mark where the feedback line leaves an output that also feeds other blocks
        if sum(1 for _ in self.source.connections()) > 1:
            self._branch_dot.addEllipse(p1, BRANCH_DOT_RADIUS, BRANCH_DOT_RADIUS)

    def _route_angled(self, start, end):
        ds = _unit(self.source.gui.direction)
        dk = _unit(self.sink.gui.direction)
        ext = CONNECTOR_EXTENSION_MINIMAL
        self._branch_dot = QPainterPath()

        if ds == dk == QPointF(1.0, 0.0):
            if end.x() >= start.x():
                self._route_forward(start, end)
            else:
                self._route_feedback(start, end, ds, dk)
            return

        # Rotated or mixed orientations: short stubs out of both ports and a
        # Z shaped link between them.
        p1 = start + ds * ext
        p2 = end - dk * ext
        self._line.lineTo(p1)
        _elbow(self._line, p1, p2, horizontal_first=ds.x() != 0)
        self._line.lineTo(end)

    def update(self):
        """
        Source and sink moved in relation to each other, redraw with new end points
        """
        self.prepareGeometryChange()
        start = self.source.gui.connection_point
        end = self.sink.gui.connection_point

        self._line.clear()
        self._line.moveTo(start)
        self._branch_dot = QPainterPath()

        if self._conn_style == StyledConnection.ConnectionStyle.CURVED:
            c1 = self.source.gui.ctrl_point
            c2 = self.sink.gui.ctrl_point
            self._line.cubicTo(c1, c2, end)
        else:
            self._route_angled(start, end)
        self._create_arrowhead()

        self._path.clear()
        self._path.addPath(self._line)
        self._path.addPath(self._arrowhead)
        self._path.addPath(self._branch_dot)
        self.setPath(self._path)

    def set_rotation(self, angle):
        self._arrow_rotation = angle

    def shape(self):
        """Only the stroke is clickable, not the area enclosed by the bends."""
        stroker = QPainterPathStroker()
        stroker.setWidth(8.0)
        shape = stroker.createStroke(self._line)
        shape.addPath(self._arrowhead)
        return shape

    def _create_arrowhead(self):
        end_point = self.sink.gui.connection_point
        direction = _unit(self.sink.gui.direction)
        self._arrowhead = _arrowhead(end_point + direction * CONNECTOR_ARROW_HEIGHT, direction)

    def paint(self, painter, option, widget):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Thin dark signal lines; invalid lines are red and dashed, like an
        # unconnected line in Simulink.
        color = colors.CONNECTION_ENABLED_COLOR
        width = 1.2
        dashed = False
        if self.isSelected():
            color = colors.HIGHLIGHT_COLOR
            width = 2.0
        elif not self.core.enabled:
            color = colors.CONNECTION_DISABLED_COLOR
            dashed = True
        elif not self.core.is_valid():
            color = colors.CONNECTION_ERROR_COLOR
            dashed = True

        pen = QPen(color)
        pen.setWidthF(width * self._line_width_factor)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        if dashed:
            pen.setDashPattern([4.0, 3.0])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._line)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(color))
        painter.drawPath(self._arrowhead)
        if not self._branch_dot.isEmpty():
            painter.drawPath(self._branch_dot)

    def mouseDoubleClickEvent(self, e):
        connection = self.core
        self.core.parent.gui.set_saved(False)
        connection.parent.connections.remove(connection)
        self.scene().removeItem(self)
        # an unconnected input shows its arrow again
        self.sink.gui.update()
