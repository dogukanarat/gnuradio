from __future__ import absolute_import, print_function

# Standard modules
import logging

import xml.etree.ElementTree as ET

from ast import literal_eval
from PyQt6.QtCore import Qt, QLineF
from PyQt6.QtGui import QBrush, QAction, QPen
from PyQt6.QtWidgets import QGraphicsView, QMenu

# Custom modules
from .canvas.block import Block
from .. import base
from .canvas.flowgraph import FlowgraphScene, Flowgraph
from .canvas import colors
from .canvas.block import GUIBlock

from ...core.generator import Generator

# Logging
log = logging.getLogger(f"grc.application.{__name__}")

DEFAULT_MAX_X = 400
DEFAULT_MAX_Y = 300

# Background grid spacing in scene units; every GRID_MAJOR_EVERY-th line is darker
GRID_SPACING = 20
GRID_MAJOR_EVERY = 5
# Zoom factor of the view that is shown as "100 %"
DEFAULT_SCALE = 0.8


class FlowgraphView(
    QGraphicsView, base.Component
):  # added base.Component so it can see platform
    def __init__(self, parent, platform, filename=None):
        super(FlowgraphView, self).__init__()
        self.setParent(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

        self.setScene(FlowgraphScene(self, platform))

        self.scalefactor = 0.8
        self.scale(self.scalefactor, self.scalefactor)

        self.setSceneRect(0, 0, DEFAULT_MAX_X, DEFAULT_MAX_Y)
        if filename is not None:
            self.readFile(filename)
        else:
            self.initEmpty()

        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.setBackgroundBrush(QBrush(colors.FLOWGRAPH_BACKGROUND_COLOR))
        self.show_grid = self.app.qsettings.value("appearance/show_grid", True, type=bool)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)

        self.isPanning = False
        self.mousePressed = False

        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        self.generator = None
        self.process = None

    def createActions(self, actions):
        log.debug("Creating actions")

    def drawBackground(self, painter, rect):
        """Plain canvas with a light engineering grid."""
        painter.fillRect(rect, colors.FLOWGRAPH_BACKGROUND_COLOR)
        if not self.show_grid:
            return
        # Skip the minor lines when they would be closer than 6 px on screen
        scale = self.transform().m11() or 1.0
        step = GRID_SPACING if GRID_SPACING * scale >= 6 else GRID_SPACING * GRID_MAJOR_EVERY
        minor, major = [], []
        left = int(rect.left()) - int(rect.left()) % step
        top = int(rect.top()) - int(rect.top()) % step
        x = left
        while x < rect.right():
            line = QLineF(x, rect.top(), x, rect.bottom())
            (major if x % (GRID_SPACING * GRID_MAJOR_EVERY) == 0 else minor).append(line)
            x += step
        y = top
        while y < rect.bottom():
            line = QLineF(rect.left(), y, rect.right(), y)
            (major if y % (GRID_SPACING * GRID_MAJOR_EVERY) == 0 else minor).append(line)
            y += step
        for lines, color in ((minor, colors.GRID_MINOR_COLOR), (major, colors.GRID_MAJOR_COLOR)):
            pen = QPen(color)
            pen.setCosmetic(True)
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawLines(lines)

    def set_grid_visible(self, visible):
        self.show_grid = visible
        self.resetCachedContent()
        self.viewport().update()

    def zoom_percent(self) -> int:
        return int(round(self.transform().m11() / DEFAULT_SCALE * 100))

    def contextMenuEvent(self, event):
        if self.scene().selected_blocks():
            block = self.scene().selected_blocks()[0]
            self.scene().clearSelection()
            block.setSelected(True)
            block.context_menu(event.globalPos())
        else:
            empty_menu = QMenu()
            no_action = QAction("No block selected", enabled=False)
            empty_menu.addAction(no_action)
            empty_menu.exec(event.globalPos())

    def createMenus(self, actions, menus):
        log.debug("Creating menus")

    def createToolbars(self, actions, toolbars):
        log.debug("Creating toolbars")

    def get_generator(self) -> Generator:
        return self.generator

    def process_is_done(self) -> bool:
        if self.process is None:
            return True
        else:
            return (False if self.process.returncode is None else True)

    def readFile(self, filename):
        tree = ET.parse(filename)

        for xml_block in tree.findall("block"):
            attrib = {}
            params = []
            block_key = xml_block.find("key").text

            for param in xml_block.findall("param"):
                key = param.find("key").text
                value = param.find("value").text
                if key.startswith("_"):
                    attrib[key] = literal_eval(value)
                else:
                    params.append((key, value))

            # Find block in tree so that we can pull out label
            try:
                block = self.platform.blocks[block_key]

                new_block = Block(block_key, block.label, attrib, params)
                self.scene.addItem(new_block)
                self.newElement.emit(new_block)
            except:
                log.warning("Block '{}' was not found".format(block_key))

        # This part no longer works now that we are using a Scene with GraphicsItems, but I'm sure there's still some way to do it
        # bounds = self.scene.itemsBoundingRect()
        # self.setSceneRect(bounds)
        # self.fitInView(bounds)

    def initEmpty(self):
        self.setSceneRect(0, 0, DEFAULT_MAX_X, DEFAULT_MAX_Y)

    def zoom(self, factor: float, anchor=QGraphicsView.ViewportAnchor.AnchorViewCenter):
        new_scalefactor = self.scalefactor * factor

        if new_scalefactor > 0.25 and new_scalefactor < 2.5:
            self.scalefactor = new_scalefactor
            self.setTransformationAnchor(anchor)
            self.setResizeAnchor(anchor)
            self.scale(factor, factor)
            main_window = getattr(self.app, "MainWindow", None)
            if main_window is not None:
                main_window.updateStatusInfo()

    def zoomOriginal(self):
        # TODO: Original scale factor as a constant?
        self.zoom(0.8 / self.scalefactor)

    def wheelEvent(self, event):
        # TODO: Support multi touch drag and drop for scrolling through the view
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier:
            factor = 1.1 if event.angleDelta().y() > 0 else (1.0 / 1.1)
            self.zoom(factor, anchor=QGraphicsView.ViewportAnchor.AnchorUnderMouse)

            # if new_scalefactor > 0.25 and new_scalefactor < 2.5:
            #     self.scalefactor = new_scalefactor
            #     self.setTransformationAnchor(QGraphicsView.NoAnchor)
            #     self.setResizeAnchor(QGraphicsView.NoAnchor)

            #     old_pos = self.mapToScene(event.pos())

            #     self.scale(factor, factor)
            #     new_pos = self.mapToScene(event.pos())

            #     delta = new_pos - old_pos
            #     self.translate(delta.x(), delta.y())

        elif event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - event.angleDelta().y())
        else:
            QGraphicsView.wheelEvent(self, event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mousePressed = True
            # This will pass the mouse move event to the scene
            super(FlowgraphView, self).mousePressEvent(event)

        elif event.button() == Qt.MouseButton.MiddleButton:
            self.isPanning = True
            self.dragPos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

        elif event.button() == Qt.MouseButton.RightButton:

            #  Check if the right click happened on a block
            #  then select this block and deselect all others
            #  Otherwise contextMenuEvent will lock for a already
            #  selected block to handle

            block = self.itemAt(event.pos())
            if block:
                self.scene().clearSelection()
                block.setSelected(True)

    def mouseMoveEvent(self, event):
        if self.isPanning:
            new_pos = event.pos()
            diff = new_pos - self.dragPos
            self.dragPos = new_pos
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - diff.x()
            )
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - diff.y()
            )
            event.accept()
        else:
            # This will pass the mouse move event to the scene
            super(FlowgraphView, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.mousePressed = False

        elif event.button() == Qt.MouseButton.MiddleButton:
            self.isPanning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()

        super(FlowgraphView, self).mouseReleaseEvent(event)

    def keyPressEvent(self, event):
        super(FlowgraphView, self).keyPressEvent(event)

    def keyReleaseEvent(self, event):
        super(FlowgraphView, self).keyPressEvent(event)

    def mouseDoubleClickEvent(self, event):
        # This will pass the double click event to the scene
        super(FlowgraphView, self).mouseDoubleClickEvent(event)
