from PyQt6.QtGui import QPainterPath, QPainterPathStroker, QPainter, QPen, QBrush, QPolygonF
from PyQt6.QtWidgets import QGraphicsPathItem, QApplication
from PyQt6.QtCore import QPointF, QRectF, Qt

from enum import Enum

from ....core.Connection import Connection as CoreConnection
from . import colors
from . import router
from ...Constants import (
    CONNECTOR_ARROW_BASE,
    CONNECTOR_ARROW_HEIGHT,
    CONNECTOR_EXTENSION_MINIMAL,
)

# Radius of the dot drawn where connections from one output branch off
BRANCH_DOT_RADIUS = 2.8


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
        self._points = None   # routed polyline as (x, y) tuples
        self._pass = None     # routing pass that produced _points
        self._trunk_x = None  # x of the shared vertical run of forward lines

        self._color1 = self._color2 = None

        self._current_port_rotations = self._current_coordinates = None

        self._rel_points = None  # connection coordinates relative to sink/source
        self._arrow_rotation = 0.0  # rotation of the arrow in radians
        self._current_cr = None  # for what_is_selected() of curved line
        self._line_path = None
        self.setFlag(QGraphicsPathItem.GraphicsItemFlag.ItemIsSelectable)
        self.update()

    # ------------------------------------------------------------- routing
    def _scene(self):
        scene = self.scene()
        if scene is None:
            gui = getattr(self.source.parent_block, "gui", None)
            scene = gui.scene() if gui is not None else None
        return scene

    def _route_pass(self):
        """Token of the scene-wide routing pass in progress, or None."""
        return getattr(self._scene(), "_route_pass", None)

    def _fast(self):
        """While blocks are dragged only cheap routes are drawn; the full router runs on release."""
        scene = self._scene()
        return bool(getattr(scene, "moving_blocks", False)) and self._route_pass() is None

    def _other_lines(self):
        """
        Segments of the other connections: (occupied, shared, siblings).
        occupied: lines of other outputs, shared: lines of our own output,
        siblings: the point lists of the lines of our own output.
        During a routing pass only lines already routed in the pass count.
        """
        current = self._route_pass()
        occupied, shared, siblings = [], [], []
        try:
            connections = self.core.parent.connections
        except AttributeError:
            return occupied, shared, siblings
        for conn in connections:
            gui = getattr(conn, "gui", None)
            if conn is self.core or gui is None or not getattr(gui, "_points", None):
                continue
            if current is not None and gui._pass is not current:
                continue
            segments = list(zip(gui._points, gui._points[1:]))
            if conn.source_port is self.source:
                shared += segments
                siblings.append(gui._points)
            else:
                occupied += segments
        return occupied, shared, siblings

    def _obstacles(self, skip=()):
        """
        Scene rectangles (left, top, right, bottom) a line must not cross:
        every block with its ports and, for blocks other than our own source
        and sink, the space right in front of each port, where that port's
        own line arrives or leaves (Simulink never runs a line across it).
        """
        rects = []
        try:
            blocks = self.core.parent.blocks
        except AttributeError:
            return rects
        own = (self.source.parent_block, self.sink.parent_block)
        approach = CONNECTOR_EXTENSION_MINIMAL + CONNECTOR_ARROW_HEIGHT
        for block in blocks:
            if block in skip:
                continue
            gui = getattr(block, "gui", None)
            if gui is None or not gui.isVisible():
                continue
            if getattr(gui, "hide_variables", False) and (block.is_variable or block.is_import):
                continue
            if block in own:
                # our own blocks: just the body, the lines start and end at it
                r = gui.mapRectToScene(QRectF(0, 0, gui.width, gui.height)).adjusted(-8, -8, 8, 8)
            else:
                # the bounding rect already includes a small margin around the block
                r = gui.sceneBoundingRect()
            for port in list(block.active_sources) + list(block.active_sinks):
                port_gui = getattr(port, "gui", None)
                if port_gui is None or port.hidden:
                    continue
                if block in own:
                    continue
                pr = port_gui.sceneBoundingRect()
                if block not in own:
                    d = _unit(port_gui.direction)
                    if port.is_sink:
                        d = QPointF(-d.x(), -d.y())
                    pr = pr.united(pr.translated(d * approach))
                r = r.united(pr)
            rects.append((r.left(), r.top(), r.right(), r.bottom()))
        return rects

    @staticmethod
    def _hits(points, rects):
        """True if the polyline through `points` runs through any rectangle."""
        for (ax, ay), (bx, by) in zip(points, points[1:]):
            if abs(ay - by) < 0.01:
                x1, x2 = sorted((ax, bx))
                for left, top, right, bottom in rects:
                    if top < ay < bottom and x1 < right and x2 > left:
                        return True
            else:
                y1, y2 = sorted((ay, by))
                for left, top, right, bottom in rects:
                    if left < ax < right and y1 < bottom and y2 > top:
                        return True
        return False

    @staticmethod
    def _on_lane(points, occupied):
        """True if the polyline runs on top of (or right next to) a line of another output."""
        for (ax, ay), (bx, by) in zip(points, points[1:]):
            for (cx, cy), (dx, dy) in occupied:
                if abs(ay - by) < 0.01 and abs(cy - dy) < 0.01 and abs(ay - cy) < router.LANE - 0.5:
                    if min(max(ax, bx), max(cx, dx)) - max(min(ax, bx), min(cx, dx)) > 1.0:
                        return True
                elif abs(ax - bx) < 0.01 and abs(cx - dx) < 0.01 and abs(ax - cx) < router.LANE - 0.5:
                    if min(max(ay, by), max(cy, dy)) - max(min(ay, by), min(cy, dy)) > 1.0:
                        return True
        return False

    @staticmethod
    def _candidates(preferred, low, high, step=router.LANE):
        """`preferred` first, then positions in [low, high] moving away from it."""
        yield preferred
        k = 1
        while preferred - k * step >= low or preferred + k * step <= high:
            for value in (preferred + k * step, preferred - k * step):
                if low <= value <= high:
                    yield value
            k += 1

    def _forward_group(self, start):
        """End points and blocks of the left-to-right lines leaving our output."""
        group = []
        for conn in self.source.connections():
            gui = getattr(conn, "gui", None)
            sink = gui.sink if gui is not None else conn.sink_port
            try:
                end = sink.gui.connection_point
                direction = _unit(sink.gui.direction)
            except Exception:
                continue
            if direction == QPointF(1.0, 0.0) and end.x() >= start[0]:
                group.append(((end.x(), end.y()), sink.parent_block, conn))
        return group

    def _route_forward(self, start, end, occupied, shared):
        """
        Left-to-right connection, routed like a Simulink signal line:
        horizontal out of the source, one vertical run, horizontal into the
        sink. Lines leaving one output share that vertical run (the trunk).
        Blocks and lines of other outputs are avoided.
        """
        group = self._forward_group(start)
        if not any(conn is self.core for _, _, conn in group):
            group.append((end, self.sink.parent_block, self.core))
        branched = len(group) > 1
        # The trunk must come out the same for every line of the group, so
        # they all use the same obstacles: everything but the source and the sinks.
        rects = self._obstacles(skip=[self.source.parent_block] + [blk for _, blk, _ in group])
        ends = [e for e, _, _ in group]
        sx, sy = start

        # A nearly straight line is drawn straight (no 1-2 px jog), as long as
        # the line starts on the block border and does not branch.
        if not branched and abs(end[1] - sy) < 5 and not self.source.gui._draws_body():
            straight = [(sx, end[1]), end]
            if not self._hits(straight, rects) and not self._on_lane(straight, occupied):
                return straight

        def simple(x, e):
            return [(x, sy), (x, e[1]), e]

        trunk = None
        current = self._route_pass()
        if current is not None:
            # reuse the trunk of a branch routed earlier in this pass
            for _, _, conn in group:
                gui = getattr(conn, "gui", None)
                if conn is not self.core and gui is not None and gui._pass is current and gui._trunk_x is not None:
                    trunk = gui._trunk_x
                    break

        if trunk is None:
            nearest = min(e[0] for e in ends)
            low = sx + 4.0
            high = max(low, nearest - 4.0)
            preferred = sx + (nearest - sx) / 2.0
            top = min([sy] + [e[1] for e in ends])
            bottom = max([sy] + [e[1] for e in ends])
            best = -1
            for x in self._candidates(preferred, low, high):
                stub = [start, (x, sy)]
                if self._hits(stub, rects):
                    continue
                # the trunk itself must not run on a line of another output
                if top < bottom and self._on_lane([(x, top), (x, bottom)], occupied):
                    continue
                clear = sum(not self._hits(simple(x, e), rects) for e in ends)
                if clear > best:
                    trunk, best = x, clear
                if clear == len(ends):
                    break
            if trunk is None:
                trunk = preferred
        self._trunk_x = trunk

        tee = (trunk, sy)
        branch = simple(trunk, end)
        own_rects = self._obstacles()
        if not self._hits(branch, own_rects) and not self._on_lane(branch, occupied):
            return [start] + branch

        # Blocks or other lines in the way: let the router find this branch's
        # way from the trunk to the input.
        if not self._fast():
            path = router.route(tee, None, end, (1.0, 0.0), own_rects, occupied, shared,
                                stub=CONNECTOR_EXTENSION_MINIMAL)
            if path:
                return [start] + path
        return [start] + branch

    def _route_general(self, start, ds, end, dk, occupied, shared):
        """Any other case (feedback, rotated blocks): the router."""
        if not self._fast():
            path = router.route(start, (ds.x(), ds.y()), end, (dk.x(), dk.y()), self._obstacles(),
                                occupied, shared, stub=CONNECTOR_EXTENSION_MINIMAL)
            if path:
                return path
        # cheap fallback: stubs out of both ports and a Z between them
        ext = CONNECTOR_EXTENSION_MINIMAL
        p1 = (start[0] + ds.x() * ext, start[1] + ds.y() * ext)
        p2 = (end[0] - dk.x() * ext, end[1] - dk.y() * ext)
        if ds.x() != 0:
            mid = (p1[0] + p2[0]) / 2.0
            middle = [(mid, p1[1]), (mid, p2[1])]
        else:
            mid = (p1[1] + p2[1]) / 2.0
            middle = [(p1[0], mid), (p2[0], mid)]
        return router.simplify([start, p1] + middle + [p2, end])

    def _route_angled(self, start, end):
        ds = _unit(self.source.gui.direction)
        dk = _unit(self.sink.gui.direction)
        start, end = (start.x(), start.y()), (end.x(), end.y())
        occupied, shared, _ = self._other_lines()
        self._trunk_x = None
        if ds == dk == QPointF(1.0, 0.0) and end[0] >= start[0]:
            points = self._route_forward(start, end, occupied, shared)
        else:
            points = self._route_general(start, ds, end, dk, occupied, shared)
        return router.simplify(points)

    def update_branch_dot(self):
        """Dot where this line leaves the other lines of the same output."""
        self._branch_dot = QPainterPath()
        if self._points and self._conn_style == StyledConnection.ConnectionStyle.ANGLED:
            _, _, siblings = self._other_lines()
            point = router.divergence(self._points, siblings)
            if point is not None and point != self._points[0] and point != self._points[-1]:
                self._branch_dot.addEllipse(QPointF(*point), BRANCH_DOT_RADIUS, BRANCH_DOT_RADIUS)
        self._rebuild_path()

    def _rebuild_path(self):
        self._path.clear()
        self._path.addPath(self._line)
        self._path.addPath(self._arrowhead)
        self._path.addPath(self._branch_dot)
        self.setPath(self._path)

    def update(self):
        """
        Source and sink moved in relation to each other, redraw with new end points
        """
        self.prepareGeometryChange()
        start = self.source.gui.connection_point
        end = self.sink.gui.connection_point

        self._line.clear()
        self._branch_dot = QPainterPath()

        if self._conn_style == StyledConnection.ConnectionStyle.CURVED:
            self._line.moveTo(start)
            c1 = self.source.gui.ctrl_point
            c2 = self.sink.gui.ctrl_point
            self._line.cubicTo(c1, c2, end)
            self._points = None
        else:
            self._points = self._route_angled(start, end)
            self._line.moveTo(QPointF(*self._points[0]))
            for point in self._points[1:]:
                self._line.lineTo(QPointF(*point))
        self._pass = self._route_pass()
        self._create_arrowhead()
        if self._pass is None:
            self.update_branch_dot()
        else:
            # the scene sets the dots once every line of the pass is routed
            self._rebuild_path()

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
