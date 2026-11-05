import re

from PyQt6.QtGui import QPen, QPainter, QBrush, QFont, QFontMetrics, QPolygonF, QColor
from PyQt6.QtCore import Qt, QPointF, QRectF, QVariant
from PyQt6.QtWidgets import QGraphicsItem

from . import colors
from ... import Constants
from ....core.ports import Port as CorePort

# Logging
import logging
import traceback
log = logging.getLogger(f"grc.application.{__name__}")

# Port names that only repeat what the port's position already says
# ("in", "out", "in1", "out0", "0", ...). They are drawn as plain arrows
# and the name is shown in the tooltip instead.
_DEFAULT_PORT_NAME = re.compile(r"^(in|out)?\d*$")

# Width of an unlabelled (arrow only) port
ARROW_PORT_WIDTH = 10.0


class Port(CorePort):
    @classmethod
    def make_cls_with_base(cls, super_cls):
        name = super_cls.__name__
        bases = (super_cls,) + cls.__bases__[:-1]
        namespace = cls.__dict__.copy()
        return type(name, bases, namespace)

    def __init__(self, parent, direction, **n):
        super(self.__class__, self).__init__(parent, direction, **n)
        self.gui = GUIPort(self, direction)

    def remove_clone(self, port):
        self.gui.scene().removeItem(port.gui)
        super(self.__class__, self).remove_clone(port)


class GUIPort(QGraphicsItem):
    """
    The graphical port. Interfaces with its underlying Port object using self.core.
    The GUIPort is always instantiated in the Port constructor.

    Note that this constructor is called before its parent GUIBlock is instantiated,
    which is why we call setParentItem() in create_shapes_and_labels().

    Geometry (in port coordinates, before the block's rotation):
    the port occupies QRectF(0, 0, width, height). Sinks sit left of the block
    with their right edge on the block border, sources sit right of the block
    with their left edge on the block border. Both point in the direction of
    the data flow.
    """

    def __init__(self, core, direction, **n):
        self.core = core
        QGraphicsItem.__init__(self)

        self.y_offset = 0
        self.height = 3 * 15.0 if self.core.dtype == 'bus' else 15.0
        self.width = ARROW_PORT_WIDTH
        self.show_name = False

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges)

        self._border_color = self._bg_color = colors.BLOCK_ENABLED_COLOR
        self._text_color = colors.FONT_COLOR

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setAcceptHoverEvents(True)

        self._hovering = False
        self.auto_hide_port_labels = False

        self.font = QFont()
        self.font.setPointSizeF(7.5)
        self.font.setBold(True)
        self.fm = QFontMetrics(self.font)

        # TODO: Move somewhere else? Not necessarily
        self.core.parent_flowgraph.gui.addItem(self)

        """ Dummy blocks instantiate ports only when a connection to them is created. """
        if self.core.parent_block.is_dummy_block:
            self.setParentItem(self.core.parent_block.gui)

    # ------------------------------------------------------------------ geometry
    def _is_connected(self):
        try:
            # connections() is a generator
            return any(True for _ in self.core.connections())
        except Exception:
            return False

    def _draws_body(self):
        """Unlabelled sink arrows disappear once a connection's arrow head takes their place."""
        if self.show_name or self.core._dir != "sink":
            return True
        return not self._is_connected()

    @property
    def connection_point(self):
        """Scene position where a connection line attaches to this port."""
        if self.core._dir == "sink":
            # The connection arrow head ends on the block border for connected
            # arrow ports, otherwise on the outer edge of the port.
            x = 0.0 if self._draws_body() else self.width
            return self.mapToScene(QPointF(x - Constants.CONNECTOR_ARROW_HEIGHT, self.height / 2.0))
        return self.mapToScene(QPointF(self.width, self.height / 2.0))

    @property
    def ctrl_point(self):
        """Control point for curved connections."""
        if self.core._dir == "sink":
            return self.mapToScene(QPointF(-100.0, self.height / 2.0))
        return self.mapToScene(QPointF(self.width + 100.0, self.height / 2.0))

    @property
    def direction(self):
        """Unit vector (scene coordinates) of the data flow at this port."""
        p0 = self.mapToScene(QPointF(0.0, 0.0))
        p1 = self.mapToScene(QPointF(1.0, 0.0))
        return p1 - p0

    def update_connections(self):
        for conn in self.core.connections():
            conn.gui.set_rotation(self.parentItem().rotation() if self.parentItem() else 0.0)
            conn.gui.update()
            # Connections from the same source share a trunk; keep them in step
            for sibling in conn.source_port.connections():
                if sibling is not conn and getattr(sibling, "gui", None) is not None:
                    sibling.gui.update()

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value: QVariant):
        if change in (QGraphicsItem.GraphicsItemChange.ItemScenePositionHasChanged,
                      QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged):
            self.update_connections()
        try:
            return QGraphicsItem.itemChange(self, change, value)
        except TypeError as e:
            # There's nothing to trace back here; messaging nature of Qt erases that.
            namestr = (
                f"{self.core.parent_block}: {self.core._dir} port {self.core.name}"
            )
            log.error(
                namestr +
                "TypeError! failed to process change message " +
                f"{e} (value: {value} / change: {change})"
            )
        except Exception as e:
            namestr = (
                f"{self.core.parent_block}: {self.core._dir} port {self.core.name}"
            )
            log.error(f"{namestr}: failed to process change message {e}")
            log.debug(
                f"{namestr}: traceback:\n" +
                "".join(traceback.format_exception(None, value=e, tb=e.__traceback__))
            )

    def create_shapes_and_labels(self):
        self.auto_hide_port_labels = self.core.parent.parent.gui.app.qsettings.value(
            'grc/auto_hide_port_labels', type=bool)
        """
        The GUI port is instantiated before its parent block. Therefore we set the parent here,
        not in the constructor. Exception: dummy block ports, see __init__() above
        """
        if not self.parentItem():
            self.setParentItem(self.core.parent_block.gui)

        self.prepareGeometryChange()
        name = self.core.name or ""
        self.show_name = (
            self.core.dtype == 'bus' or
            self.core.domain == Constants.GR_MESSAGE_DOMAIN or
            not _DEFAULT_PORT_NAME.match(name)
        )
        if self.show_name:
            self.width = float(max(18, self.fm.horizontalAdvance(name) + 14))
        else:
            self.width = ARROW_PORT_WIDTH

        dtype = "message" if self.core.domain == Constants.GR_MESSAGE_DOMAIN else (self.core.dtype or "any")
        tip = f"{name or self.core._dir}  ·  {dtype}"
        try:
            vlen = int(self.core.vlen)
            if vlen > 1:
                tip += f" × {vlen}"
        except Exception:
            pass
        self.setToolTip(tip)

        self._update_colors()
        self.update_connections()

    @property
    def _show_label(self) -> bool:
        return self.show_name and (self._hovering or not self.auto_hide_port_labels)

    def _update_colors(self):
        """
        Get the color that represents this port's type.
        TODO: Codes differ for ports where the vec length is 1 or greater than 1.
        """
        if not self.core.parent.enabled:
            color = QColor(colors.BORDER_COLOR_DISABLED)
        elif self.core.domain == Constants.GR_MESSAGE_DOMAIN:
            color = colors.PORT_TYPE_TO_COLOR.get('message')
        else:
            color = colors.PORT_TYPE_TO_COLOR.get(self.core.dtype) or colors.PORT_TYPE_TO_COLOR.get('')
        color = QColor(color)
        self._bg_color = color
        self._border_color = color.darker(150)
        # Readable label on top of the type color
        luminance = 0.299 * color.redF() + 0.587 * color.greenF() + 0.114 * color.blueF()
        self._text_color = QColor("#16202B") if luminance > 0.6 else QColor("#FFFFFF")

    def _outline(self):
        w, h = self.width, self.height
        if not self.show_name:
            # A plain arrow head pointing along the data flow
            return QPolygonF([QPointF(1.0, 2.0), QPointF(w, h / 2.0), QPointF(1.0, h - 2.0)])
        # A tag: flat back, pointed front
        tip = min(5.0, w / 3.0)
        return QPolygonF([
            QPointF(0.0, 0.5), QPointF(w - tip, 0.5), QPointF(w, h / 2.0),
            QPointF(w - tip, h - 0.5), QPointF(0.0, h - 0.5),
        ])

    def paint(self, painter, option, widget):
        if self.core.hidden:
            return
        if not self._draws_body():
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(self._border_color)
        pen.setWidthF(1.0)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(pen)
        painter.setBrush(QBrush(self._bg_color))
        painter.drawPolygon(self._outline())

        if not self._show_label:
            return

        # TODO: Adjustments for finer rotation values if required (eg. 15, 30)
        block_rotation = self.parentItem().rotation()
        painter.setPen(QPen(self._text_color))
        painter.setFont(self.font)
        text_rect = QRectF(1.0, 0.0, self.width - 6.0, self.height)
        if block_rotation == 180:
            # keep the text upright
            painter.translate(self.width, self.height)
            painter.rotate(180)
            text_rect = QRectF(5.0, 0.0, self.width - 6.0, self.height)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, self.core.name)

    def center(self):
        return QPointF(self.x() + self.width / 2, self.y() + self.height / 2)

    def boundingRect(self):
        return QRectF(0, 0, self.width, self.height)

    def hoverEnterEvent(self, event):
        self._hovering = True
        self.update()
        return QGraphicsItem.hoverEnterEvent(self, event)

    def hoverLeaveEvent(self, event):
        self._hovering = False
        self.update()
        return QGraphicsItem.hoverLeaveEvent(self, event)
