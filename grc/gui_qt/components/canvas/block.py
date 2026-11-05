import logging

from PyQt6.QtGui import QPen, QPainter, QPainterPath, QPolygonF, QBrush, QFont, QFontMetrics, QColor, QAction
from PyQt6.QtCore import Qt, QPointF, QRectF, QUrl
from PyQt6.QtWidgets import QGraphicsItem, QApplication, QGraphicsTextItem

from . import colors
from ... import Constants
from ... import Utils
from ....core.blocks.block import Block as CoreBlock
from ....core.utils import flow_graph_complexity

from ..dialogs import PropsDialog

# Logging
log = logging.getLogger(f"grc.application.{__name__}")

LONG_VALUE = 20  # maximum length of a param string.
# if exceeded, '...' will be displayed

DO_NOT_HIDE_ID_BLOCKS = ["options"]

# Block layout (scene units)
TITLE_HEIGHT = 30       # band holding the block name
ROW_HEIGHT = 20         # one parameter row
BOTTOM_PADDING = 5
TEXT_PADDING = 10       # left/right padding of the text
BLOCK_RADIUS = 3.0
SELECTION_PADDING = 6   # gap between block and selection frame
LABEL_BELOW_HEIGHT = 16  # name drawn under symbol shaped blocks

# Elementary math blocks drawn as symbols instead of boxes
OPERATOR_SYMBOLS = {
    "blocks_add_xx": "+",
    "blocks_sub_xx": "\u2212",
    "blocks_multiply_xx": "\u00d7",
    "blocks_divide_xx": "\u00f7",
}
GAIN_BLOCKS = {"blocks_multiply_const_vxx", "blocks_multiply_const_xx"}
# Input positions on a circle (degrees, counter-clockwise from the output on
# the right) by number of inputs, as on Simulink's round sum block
CIRCLE_INPUT_ANGLES = {0: (), 1: (180,), 2: (180, 270), 3: (90, 180, 270)}


class Block(CoreBlock):
    """
    A block. Accesses its graphical representation with self.gui.
    """
    @classmethod
    def make_cls_with_base(cls, super_cls):
        name = super_cls.__name__
        bases = (super_cls,) + cls.__bases__[:-1]
        namespace = cls.__dict__.copy()
        return type(name, bases, namespace)

    def __init__(self, parent, **n):
        super(self.__class__, self).__init__(parent, **n)

        self.width = 50  # will change immediately after the first paint
        self.block_label = self.key

        self.old_data = None

        if "rotation" not in self.states.keys():
            self.states["rotation"] = 0.0

        self.gui = GUIBlock(self, parent)

    def import_data(self, name, states, parameters, **_):
        super(self.__class__, self).import_data(name, states, parameters, **_)
        self.gui.setPos(*self.states["coordinate"])
        self.gui.setRotation(self.states["rotation"])
        self.rewrite()
        self.gui.create_shapes_and_labels()

    def update_bus_logic(self):
        for direc in {'source', 'sink'}:
            if direc == 'source':
                ports = self.sources
                ports_gui = self.filter_bus_port(self.sources)
            else:
                ports = self.sinks
                ports_gui = self.filter_bus_port(self.sinks)
            if 'bus' in map(lambda a: a.dtype, ports):
                for port in ports_gui:
                    self.parent_flowgraph.gui.removeItem(port.gui)
        super(self.__class__, self).update_bus_logic()


class GUIBlock(QGraphicsItem):
    """
    The graphical representation of a block. Accesses the actual block with self.core.
    """

    def __init__(self, core, parent, **n):
        super(GUIBlock, self).__init__()
        self.core = core
        self.parent = parent
        self.font = QFont()
        self.font.setPointSizeF(9.0)
        self.font.setBold(True)
        self.param_name_font = QFont()
        self.param_name_font.setPointSizeF(8.5)
        self.param_value_font = QFont(self.param_name_font)
        self.param_value_font.setWeight(QFont.Weight.Medium)
        self.symbol_font = QFont()
        self.symbol_font.setPointSizeF(11.0)
        self.symbol_font.setBold(True)
        self.op_font = QFont()
        self.op_font.setPointSizeF(17.0)
        self.op_font.setBold(True)
        self._rows = []
        self._title_width = 0
        self.shape_kind, self.symbol, self.label_below = None, "", False
        self._bounds = QRectF(0, 0, 50, 35)
        self.markup_item = QGraphicsTextItem(self)

        self.create_shapes_and_labels()

        if "coordinate" not in self.core.states.keys():
            self.core.states["coordinate"] = (500, 300)
            self.setPos(*self.core.states["coordinate"])

        self.old_pos = (self.x(), self.y())
        self.new_pos = (self.x(), self.y())
        self.moving = False

        self.props_dialog = None
        self.right_click_menu = None

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsScenePositionChanges)

    def _is_item_visible(self, item) -> bool:
        if item.value is not None and item.hide == "none":
            return True
        if item.dtype == "id":
            if self.force_show_id or (self.core.key in DO_NOT_HIDE_ID_BLOCKS):
                return True
        return False

    def _load_settings(self, qsettings) -> None:
        """Load settings from qsettings"""
        self.force_show_id = qsettings.value("grc/show_block_ids", type=bool)
        self.hide_variables = qsettings.value("grc/hide_variables", type=bool)
        self.hide_disabled_blocks = qsettings.value(
            "grc/hide_disabled_blocks", type=bool
        )
        self.snap_to_grid = qsettings.value("grc/snap_to_grid", type=bool)
        self.show_complexity = qsettings.value("grc/show_complexity", type=bool)
        self.show_block_comments = qsettings.value("grc/show_block_comments", type=bool)
        self.show_param_expr = qsettings.value("grc/show_param_expr", type=bool)
        self.show_param_val = qsettings.value("grc/show_param_val", type=bool)

    def _param_lines(self):
        """The (name, value, is_valid) rows shown inside the block."""
        rows = []
        if self.core.is_dummy_block:
            return [("key", self.core.key, False)]
        for key, item in self.core.params.items():
            if not self._is_item_visible(item):
                continue
            value = item.value
            try:
                is_evaluated = item.value != str(item.get_evaluated())
            except Exception:
                is_evaluated = False

            display_value = ""
            # Include the value defined by the user (after evaluation)
            if not is_evaluated or self.show_param_val or not self.show_param_expr:
                display_value += item.options[value] if value in item.options else value  # TODO: pretty_print
            # Include the expression that was evaluated to get the value
            if is_evaluated and self.show_param_expr:
                display_value = value + "=" + display_value if display_value else value

            if len(display_value) > LONG_VALUE:
                display_value = display_value[:LONG_VALUE - 3] + '...'
            rows.append((item.name, display_value, item.is_valid()))
        return rows

    def _shape_for_block(self):
        """Simulink style symbols for a few elementary math blocks."""
        if self.core.is_dummy_block:
            return None, ""
        key = self.core.key
        if key in OPERATOR_SYMBOLS and self._fits_circle():
            return "op", OPERATOR_SYMBOLS[key]
        if key in GAIN_BLOCKS:
            const = self.core.params.get("const")
            text = const.value if const is not None else "K"
            if len(text) > 12:
                text = text[:11] + "…"
            return "gain", text
        return None, ""

    def _fits_circle(self):
        """
        A circle has room for one output (0 degrees) and up to three inputs
        (90, 180 and 270 degrees). Other operator blocks are drawn as boxes.
        """
        sinks, sources = self.core.active_sinks, self.core.active_sources
        if len(sinks) > max(CIRCLE_INPUT_ANGLES) or len(sources) != 1:
            return False
        return all(p.dtype != "bus" and p.domain != Constants.GR_MESSAGE_DOMAIN for p in sinks + sources)

    def _place_circle_ports(self):
        """
        Put the ports of a circle block on its compass points, each pointing
        at the centre, so lines always meet the circle at a right angle.
        """
        radius = self.width / 2.0
        cx = cy = radius
        sinks = self.core.active_sinks
        for port, angle in zip(sinks, CIRCLE_INPUT_ANGLES[len(sinks)]):
            g = port.gui
            if angle == 180:      # left, flowing right
                g.setRotation(0)
                g.setPos(cx - radius - g.width, cy - g.height / 2)
            elif angle == 90:     # top, flowing down
                g.setRotation(90)
                g.setPos(cx + g.height / 2, cy - radius - g.width)
            else:                 # 270: bottom, flowing up
                g.setRotation(270)
                g.setPos(cx - g.height / 2, cy + radius + g.width)
            g.update_connections()
        for port in self.core.active_sources:
            port.gui.setRotation(0)
            port.gui.setPos(cx + radius, cy - port.gui.height / 2)
            port.gui.update_connections()

    def _label_rect(self):
        """Where the name of a symbol shaped block is written (block coordinates)."""
        if self.shape_kind == "op":
            # below and to the right, clear of a line entering at the bottom
            return QRectF(self.width / 2 + 8, self.height - 2, self._title_width + 4, LABEL_BELOW_HEIGHT)
        half = self._title_width / 2 + 2
        return QRectF(self.width / 2 - half, self.height + 3, 2 * half, LABEL_BELOW_HEIGHT)

    def create_shapes_and_labels(self):
        qsettings = getattr(QApplication.instance(), 'qsettings', None)
        if qsettings is None:
            platform = getattr(self.core, 'parent_platform', None)
            config = getattr(platform, 'config', None)
            qsettings = getattr(config, 'qsettings', None)
        if qsettings is None:
            from PyQt6.QtCore import QSettings
            qsettings = QSettings()
        self._load_settings(qsettings)
        self.prepareGeometryChange()

        self._rows = self._param_lines()
        self.shape_kind, self.symbol = self._shape_for_block()
        self.label_below = self.shape_kind is not None

        # Check if we need to increase the height to fit all the ports
        def get_min_height_for_ports(ports):
            min_height = (
                2 * Constants.PORT_BORDER_SEPARATION +
                len(ports) * Constants.PORT_SEPARATION
            )
            # If any of the ports are bus ports - make the min height larger
            if any([p.dtype == "bus" for p in ports]):
                min_height = (
                    2 * Constants.PORT_BORDER_SEPARATION +
                    sum(
                        port.gui.height + Constants.PORT_SPACING
                        for port in ports
                        if port.dtype == "bus"
                    ) - Constants.PORT_SPACING
                )

            else:
                if ports:
                    min_height -= ports[-1].gui.height
            return min_height

        port_height = max(
            get_min_height_for_ports(self.core.active_sinks),
            get_min_height_for_ports(self.core.active_sources),
        )

        title_fm = QFontMetrics(self.font)
        name_fm = QFontMetrics(self.param_name_font)
        value_fm = QFontMetrics(self.param_value_font)
        self._title_width = title_fm.horizontalAdvance(self.core.label)

        if self.shape_kind == "op":
            self.width = self.height = 44
        elif self.shape_kind == "gain":
            symbol_fm = QFontMetrics(self.symbol_font)
            self.width = max(64, symbol_fm.horizontalAdvance(self.symbol) * 1.6 + 30)
            self.height = max(48, port_height)
        else:
            # Height: title band plus one row per visible parameter
            self.height = max(TITLE_HEIGHT + ROW_HEIGHT * len(self._rows) + BOTTOM_PADDING, 35, port_height)
            # Width: widest line of text
            largest_width = self._title_width
            for name, value, _ in self._rows:
                row_width = name_fm.horizontalAdvance(name + ": ") + value_fm.horizontalAdvance(value)
                largest_width = max(largest_width, row_width)
            self.width = largest_width + 2 * TEXT_PADDING

        markup_text = ""
        if self.show_complexity and self.core.key == "options":
            complexity = flow_graph_complexity.calculate(self.parent)
            markup_text = f"<b>Complexity: {Utils.num_to_str(complexity)} bal</b><br>"

        if self.core.comment:
            comment_w_line_breaks = self.core.comment.replace("\n", "<br>")
            markup_text += f"{comment_w_line_breaks}"

        self.markup_item.setPos(0, self._label_rect().bottom() if self.label_below else self.height)
        self.markup_item.setDefaultTextColor(
            colors.COMMENT_COLOR if self.core.enabled else colors.COMMENT_COLOR_DISABLED)
        self.markup_item.setHtml(markup_text)
        self.markup_item.setVisible(self.show_block_comments)

        # Update the position and size of all the ports. The ports compute
        # their own width first, because sinks hang off the left border.
        for ports in (self.core.active_sources, self.core.active_sinks):
            for port in ports:
                port.gui.create_shapes_and_labels()

        bussified = (
            self.core.current_bus_structure["source"],
            self.core.current_bus_structure["sink"],
        )
        if self.shape_kind == "op":
            self._place_circle_ports()
            bussified = ()
        for ports, has_busses in zip(
            (self.core.active_sources, self.core.active_sinks), bussified
        ):
            if not ports:
                continue
            port_separation = (
                Constants.PORT_SEPARATION
                if not has_busses
                else ports[0].gui.height + Constants.PORT_SPACING
            )
            offset = (
                self.height - (len(ports) - 1) * port_separation - ports[0].gui.height
            ) / 2
            for port in ports:
                port.gui.setRotation(0)
                if port._dir == "sink":
                    port.gui.setPos(-port.gui.width, offset)
                else:
                    # for the gain triangle this is its tip
                    port.gui.setPos(self.width, offset)
                port.gui.update_connections()

                offset += (
                    Constants.PORT_SEPARATION
                    if not has_busses
                    else port.gui.height + Constants.PORT_SPACING
                )

        self._update_colors()
        self._update_bounds()
        self.setTransformOriginPoint(self.width / 2, self.height / 2)

    def _update_bounds(self):
        margin = SELECTION_PADDING + 4
        left, right = -margin, self.width + margin
        bottom = self.height + margin
        if self.label_below:
            label = self._label_rect()
            left = min(left, label.left() - margin)
            right = max(right, label.right() + margin)
            bottom = max(bottom, label.bottom() + margin)
        self._bounds = QRectF(left, -margin, right - left, bottom + margin)

    def create_port_labels(self):
        for ports in (self.core.active_sinks, self.core.active_sources):
            for port in ports:
                port.gui.create_shapes_and_labels()

    def _update_colors(self):
        def get_bg():
            """
            Get the background color for this block
            Explicit is better than a chain of if/else expressions,
            so this was extracted into a nested function.
            """
            if self.core.is_dummy_block:
                return colors.MISSING_BLOCK_BACKGROUND_COLOR
            if self.core.state == "bypassed":
                return colors.BLOCK_BYPASSED_COLOR
            if self.core.state == "enabled":
                if self.core.deprecated:
                    return colors.BLOCK_DEPRECATED_BACKGROUND_COLOR
                if self._is_definition_block():
                    return colors.VARIABLE_BACKGROUND_COLOR
                return colors.BLOCK_ENABLED_COLOR
            return colors.BLOCK_DISABLED_COLOR

        self._bg_color = get_bg()

    def _is_definition_block(self):
        """Blocks without ports that only define things (variables, imports, options)."""
        return (
            not self.core.active_sources and not self.core.active_sinks and
            (self.core.is_variable or self.core.is_import or self.core.key in DO_NOT_HIDE_ID_BLOCKS)
        )

    def move(self, x, y):
        self.moveBy(x, y)
        self.core.states["coordinate"] = (self.x(), self.y())

    def _border_pen(self):
        color = colors.BORDER_COLOR
        style = Qt.PenStyle.SolidLine
        width = 1.3
        if self.core.is_dummy_block:
            color = colors.MISSING_BLOCK_BORDER_COLOR
        elif self.core.deprecated:
            color = colors.BLOCK_DEPRECATED_BORDER_COLOR
        elif self.core.state == "disabled":
            color = colors.BORDER_COLOR_DISABLED
            style = Qt.PenStyle.DashLine
        elif self.core.state == "bypassed":
            style = Qt.PenStyle.DashDotLine
        elif self._is_definition_block():
            color = colors.VARIABLE_BORDER_COLOR
            style = Qt.PenStyle.DashLine
            width = 1.0
        pen = QPen(color)
        pen.setWidthF(width)
        pen.setStyle(style)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        return pen

    def _outline(self):
        path = QPainterPath()
        w, h = self.width, self.height
        if self.shape_kind == "op":
            path.addEllipse(QRectF(0, 0, w, h))
        elif self.shape_kind == "gain":
            path.addPolygon(QPolygonF([QPointF(0, 0), QPointF(w, h / 2), QPointF(0, h), QPointF(0, 0)]))
            path.closeSubpath()
        else:
            path.addRoundedRect(QRectF(0, 0, w, h), BLOCK_RADIUS, BLOCK_RADIUS)
        return path

    def paint(self, painter, option, widget):
        if (self.hide_variables and (self.core.is_variable or self.core.is_import)) or (self.hide_disabled_blocks and not self.core.enabled):
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        outline = self._outline()

        # Soft drop shadow for enabled blocks
        if self.core.enabled and not self._is_definition_block():
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(colors.BLOCK_SHADOW_COLOR))
            painter.drawPath(outline.translated(0, 2))

        painter.setPen(self._border_pen())
        painter.setBrush(QBrush(self._bg_color))
        painter.drawPath(outline)

        if self.isSelected():
            self._paint_selection(painter)

        enabled = self.core.state != "disabled"
        valid = self.core.is_valid()
        title_color = colors.FONT_COLOR if valid else colors.ERROR_FONT_COLOR
        if not enabled:
            title_color = colors.BORDER_COLOR_DISABLED

        # Adjust the painter if parent block is 180 degrees rotated
        if self.rotation() == 180:
            painter.translate(self.width / 2, self.height / 2)
            painter.rotate(180)
            painter.translate(-self.width / 2, -self.height / 2)

        if self.shape_kind is not None:
            self._paint_symbol(painter, title_color if valid else colors.ERROR_FONT_COLOR)
            # Name under the symbol, like a Simulink block label
            painter.setFont(self.font)
            painter.setPen(QPen(title_color))
            align = Qt.AlignmentFlag.AlignLeft if self.shape_kind == "op" else Qt.AlignmentFlag.AlignHCenter
            painter.drawText(self._label_rect(), align | Qt.AlignmentFlag.AlignTop, self.core.label)
        else:
            self._paint_text(painter, title_color, enabled)

        if not valid and enabled:
            self._paint_error_badge(painter)

    def _paint_text(self, painter, title_color, enabled):
        # Title: centred in the top band, or in the whole block when it has no rows
        painter.setFont(self.font)
        painter.setPen(QPen(title_color))
        if self._rows:
            title_rect = QRectF(0, 4, self.width, TITLE_HEIGHT - 6)
        else:
            title_rect = QRectF(0, 0, self.width, self.height)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignCenter, self.core.label)

        name_color = colors.PARAM_NAME_COLOR if enabled else colors.BORDER_COLOR_DISABLED
        value_color = colors.PARAM_VALUE_COLOR if enabled else colors.BORDER_COLOR_DISABLED
        name_fm = QFontMetrics(self.param_name_font)
        y = TITLE_HEIGHT
        for name, value, is_valid in self._rows:
            label = name + ": "
            painter.setFont(self.param_name_font)
            painter.setPen(QPen(name_color if is_valid else colors.ERROR_FONT_COLOR))
            painter.drawText(QRectF(TEXT_PADDING, y, self.width, ROW_HEIGHT),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, label)
            painter.setFont(self.param_value_font)
            painter.setPen(QPen(value_color if is_valid else colors.ERROR_FONT_COLOR))
            painter.drawText(QRectF(TEXT_PADDING + name_fm.horizontalAdvance(label), y, self.width, ROW_HEIGHT),
                             Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, value)
            y += ROW_HEIGHT

    def _paint_symbol(self, painter, color):
        painter.setPen(QPen(color))
        if self.shape_kind == "op":
            painter.setFont(self.op_font)
            painter.drawText(QRectF(0, 0, self.width, self.height), Qt.AlignmentFlag.AlignCenter, self.symbol)
        else:
            painter.setFont(self.symbol_font)
            # The value sits in the wide part of the triangle. When the block is
            # turned around the painter is flipped too, so mirror the box.
            x = 4 if self.rotation() != 180 else self.width * 0.38 - 4
            painter.drawText(QRectF(x, 0, self.width * 0.62, self.height), Qt.AlignmentFlag.AlignCenter, self.symbol)

    def _paint_selection(self, painter):
        pad = SELECTION_PADDING
        rect = QRectF(-pad, -pad, self.width + 2 * pad, self.height + 2 * pad)
        if self.label_below:
            # include the name drawn next to symbol shaped blocks
            rect = rect.united(self._label_rect().adjusted(-2, -2, 2, 2))
        pen = QPen(colors.HIGHLIGHT_COLOR)
        pen.setWidthF(1.3)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.save()
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect)
        painter.setPen(QPen(colors.HIGHLIGHT_COLOR))
        painter.setBrush(QBrush(colors.FLOWGRAPH_BACKGROUND_COLOR))
        for corner in (rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight()):
            painter.drawRect(QRectF(corner.x() - 2.5, corner.y() - 2.5, 5, 5))
        painter.restore()

    def _paint_error_badge(self, painter):
        r = 6.0
        center = QPointF(self.width - 1, 1) if self.shape_kind is None else QPointF(self.width / 2, -1)
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(colors.ERROR_FONT_COLOR))
        painter.drawEllipse(center, r, r)
        painter.setPen(QPen(QColor("#FFFFFF")))
        font = QFont(self.font)
        font.setPointSizeF(7)
        painter.setFont(font)
        painter.drawText(QRectF(center.x() - r, center.y() - r, 2 * r, 2 * r), Qt.AlignmentFlag.AlignCenter, "!")
        painter.restore()

    def boundingRect(self):
        return self._bounds

    def set_states(self, states):
        for k, v in states.items():
            self.core.states[k] = v

        self.setPos(*self.core.states["coordinate"])
        self.setRotation(self.core.states["rotation"])

    def mousePressEvent(self, e):
        super(self.__class__, self).mousePressEvent(e)
        log.debug(f"{self} clicked")
        url_prefix = str(self.core.parent_platform.config.wiki_block_docs_url_prefix)
        QApplication.instance().WikiTab.setURL(QUrl(url_prefix + self.core.label.replace(" ", "_")))

        self.moveToTop()

    def context_menu(self, pos):
        self.right_click_menu = self.scene()._app().MainWindow.menus["edit"]
        example_action = QAction("Examples...")
        example_action.triggered.connect(self.view_examples)
        self.right_click_menu.addAction(example_action)
        self.right_click_menu.exec(pos)

    def view_examples(self):
        self.scene().app.MainWindow.example_browser_triggered(key_filter=self.core.key)

    def mouseDoubleClickEvent(self, e):
        self.open_properties()
        super(self.__class__, self).mouseDoubleClickEvent(e)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionChange and self.scene():
            x = value.x()
            y = value.y()

            # Snap to grid if enabled
            if self.snap_to_grid:
                grid_size = 10
                x = round(x / grid_size) * grid_size
                y = round(y / grid_size) * grid_size

            # Prevent dragging off top/left canvas
            x = max(0, x)
            y = max(0, y)

            value.setX(x)
            value.setY(y)
            return value

        return super().itemChange(change, value)

    def rotate(self, rotation):
        log.debug(f"Rotating {self.core.name}")
        new_rotation = (self.rotation() + rotation) % 360
        self.setRotation(new_rotation)
        self.core.states["rotation"] = new_rotation
        self.create_shapes_and_labels()
        for con in self.core.connections():
            con.gui.set_rotation(new_rotation)
            con.gui.update()

    def moveToTop(self):
        # TODO: Is there a simpler way to do this?
        self.setZValue(self.scene().getMaxZValue() + 1)

    def center(self):
        return QPointF(self.x() + self.width / 2, self.y() + self.height / 2)

    def open_properties(self):
        self.props_dialog = PropsDialog(self.core, self.force_show_id)
        self.props_dialog.show()
