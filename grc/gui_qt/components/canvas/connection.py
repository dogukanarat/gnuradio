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
BRANCH_DOT_RADIUS = 3.2
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
    def _forward_siblings(self):
        """
        End points of all connections leaving the same source port that run
        left-to-right in the same orientation as this one (including this one).
        """
        start = self.source.gui.connection_point
        ds = _unit(self.source.gui.direction)
        ends = []
        for conn in self.source.connections():
            gui = getattr(conn, "gui", None)
            sink = gui.sink if gui is not None else conn.sink_port
            try:
                end = sink.gui.connection_point
                dk = _unit(sink.gui.direction)
            except Exception:
                continue
            if dk != ds:
                continue
            along = (end - start).x() * ds.x() + (end - start).y() * ds.y()
            if along >= 0:
                ends.append(end)
        return ends

    def _route_angled(self, start, end):
        ds = _unit(self.source.gui.direction)
        dk = _unit(self.sink.gui.direction)
        ext = CONNECTOR_EXTENSION_MINIMAL
        self._branch_dot = QPainterPath()

        if ds == dk:
            delta = end - start
            along = delta.x() * ds.x() + delta.y() * ds.y()
            if along >= 0:
                # Forward connection. All forward connections of one source
                # share the first bend, so they read as one trunk with branches.
                siblings = self._forward_siblings()
                trunk = along / 2.0
                if len(siblings) > 1:
                    # bend half way to the nearest of the sinks
                    trunk = min(((e - start).x() * ds.x() + (e - start).y() * ds.y()) / 2.0
                                for e in siblings)
                bend = start + ds * trunk
                self._line.lineTo(bend)
                if ds.x() != 0:
                    self._line.lineTo(QPointF(bend.x(), end.y()))
                else:
                    self._line.lineTo(QPointF(end.x(), bend.y()))
                self._line.lineTo(end)
                if len(siblings) > 1:
                    self._branch_dot.addEllipse(bend, BRANCH_DOT_RADIUS, BRANCH_DOT_RADIUS)
                return

            if ds.x() != 0:
                # Feedback connection: leave the source, run below both
                # blocks and come back into the sink.
                p1 = start + ds * ext
                p2 = end - dk * ext
                blocks = [self.source.parent_block.gui, self.sink.parent_block.gui]
                below = max(b.sceneBoundingRect().bottom() for b in blocks) + FEEDBACK_CLEARANCE
                self._line.lineTo(p1)
                self._line.lineTo(QPointF(p1.x(), below))
                self._line.lineTo(QPointF(p2.x(), below))
                self._line.lineTo(p2)
                self._line.lineTo(end)
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

        color = colors.CONNECTION_ENABLED_COLOR
        width = 1.4
        if self.isSelected():
            color = colors.HIGHLIGHT_COLOR
            width = 2.2
        elif not self.core.enabled:
            color = colors.CONNECTION_DISABLED_COLOR
        elif not self.core.is_valid():
            color = colors.CONNECTION_ERROR_COLOR

        pen = QPen(color)
        pen.setWidthF(width * self._line_width_factor)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        if not self.core.enabled:
            pen.setStyle(Qt.PenStyle.DashLine)
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
