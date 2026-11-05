"""
Copyright 2026 The GNU Radio Contributors
This file is part of GNU Radio

SPDX-License-Identifier: GPL-2.0-or-later

Tabbed ribbon toolbar for the main window.

The ribbon only arranges the main window's existing QActions into tabs and
labelled groups; it does not own any behaviour. Each button mirrors its
action (enabled state, checked state, tooltip) and triggers it on click.
"""

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QSizePolicy,
                             QTabWidget, QToolBar, QToolButton, QVBoxLayout,
                             QWidget)

from . import icons

BIG_ICON = QSize(26, 26)
SMALL_ICON = QSize(16, 16)


class RibbonButton(QToolButton):
    """A tool button that mirrors a QAction but keeps its own short label."""

    def __init__(self, action, label, big=True, parent=None):
        super().__init__(parent)
        self._action = action
        self.setText(label)
        self.setIcon(action.icon())
        self.setAutoRaise(True)
        self.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        if big:
            self.setObjectName("ribbon_big")
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            self.setIconSize(BIG_ICON)
            self.setMinimumWidth(52)
            self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        else:
            self.setObjectName("ribbon_small")
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            self.setIconSize(SMALL_ICON)
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCheckable(action.isCheckable())
        self.clicked.connect(self._clicked)
        action.changed.connect(self._sync)
        self._sync()

    def _clicked(self):
        if self._action.isCheckable():
            # QAction.trigger() flips the checked state itself
            self._action.trigger()
            self.setChecked(self._action.isChecked())
        else:
            self._action.trigger()

    def _sync(self):
        action = self._action
        self.setEnabled(action.isEnabled())
        if action.isCheckable():
            self.setChecked(action.isChecked())
        tip = action.text().replace("&", "")
        shortcut = action.shortcut().toString()
        if shortcut:
            tip = "{0}  ({1})".format(tip, shortcut)
        if action.statusTip() and action.statusTip() != tip:
            tip = "<b>{0}</b><br>{1}".format(tip, action.statusTip())
        self.setToolTip(tip)
        self.setStatusTip(action.statusTip())


class RibbonGroup(QFrame):
    """A labelled group of buttons inside a ribbon tab."""

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("ribbon_group")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(6, 2, 6, 0)
        outer.setSpacing(0)
        self._row = QHBoxLayout()
        self._row.setContentsMargins(0, 0, 0, 0)
        self._row.setSpacing(2)
        outer.addLayout(self._row, 1)
        label = QLabel(title.upper())
        label.setObjectName("ribbon_group_title")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        outer.addWidget(label)

    def add_big(self, action, label, name=None):
        button = RibbonButton(action, label, big=True)
        if name:
            button.setObjectName(name)
        if name == "ribbon_run" and icons.has("execute"):
            # The run button sits on an accent fill, so it needs a light glyph
            button.setIcon(icons.icon("execute", "#FFFFFF", "#F4F7FB"))
        self._row.addWidget(button)
        return button

    def add_column(self, entries):
        """Stack up to three small buttons vertically. entries: [(action, label)]"""
        column = QVBoxLayout()
        column.setContentsMargins(0, 2, 0, 2)
        column.setSpacing(0)
        for action, label in entries:
            column.addWidget(RibbonButton(action, label, big=False))
        column.addStretch(1)
        self._row.addLayout(column)


class RibbonPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ribbon_page")
        # plain QWidgets only paint a style sheet background with this flag
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 4, 4, 2)
        self._layout.setSpacing(0)
        self._layout.addStretch(1)

    def add_group(self, title):
        group = RibbonGroup(title)
        self._layout.insertWidget(self._layout.count() - 1, group)
        return group


class Ribbon(QTabWidget):
    """The tab widget holding the ribbon pages."""

    HEIGHT = 112

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ribbon")
        self.setDocumentMode(True)
        self.setUsesScrollButtons(False)
        self.setFixedHeight(self.HEIGHT)
        self.tabBar().setObjectName("ribbon_tabs")
        self.tabBar().setExpanding(False)
        self.tabBar().setDrawBase(False)

    def add_page(self, title):
        page = RibbonPage()
        self.addTab(page, title.upper())
        return page


class RibbonToolBar(QToolBar):
    """A fixed toolbar that hosts the ribbon at the top of the main window."""

    def __init__(self, ribbon, parent=None):
        super().__init__("Ribbon", parent)
        self.setObjectName("_RibbonTb")
        self.setMovable(False)
        self.setFloatable(False)
        self.setAllowedAreas(Qt.ToolBarArea.TopToolBarArea)
        self.setContentsMargins(0, 0, 0, 0)
        self.layout().setContentsMargins(0, 0, 0, 0)
        self.layout().setSpacing(0)
        self.addWidget(ribbon)
        self.ribbon = ribbon


def build_ribbon(actions):
    """Arrange the main window actions (a dict of QAction) into a ribbon."""
    ribbon = Ribbon()
    a = actions

    # --- Flowgraph -------------------------------------------------------
    page = ribbon.add_page("Flowgraph")
    g = page.add_group("File")
    g.add_big(a["new"], "New")
    g.add_big(a["open"], "Open")
    g.add_big(a["save"], "Save")
    g.add_column([(a["save_as"], "Save As"), (a["close"], "Close"), (a["screen_capture"], "Screenshot")])

    g = page.add_group("Clipboard")
    g.add_big(a["paste"], "Paste")
    g.add_column([(a["cut"], "Cut"), (a["copy"], "Copy"), (a["delete"], "Delete")])

    g = page.add_group("Edit")
    g.add_column([(a["undo"], "Undo"), (a["redo"], "Redo"), (a["select_all"], "Select All")])
    g.add_column([(a["rotate_ccw"], "Rotate Left"), (a["rotate_cw"], "Rotate Right"),
                  (a["autoconnect"], "Autoconnect")])

    g = page.add_group("Library")
    g.add_big(a["find"], "Add Block")
    g.add_big(a["example_browser"], "Examples")

    g = page.add_group("Simulation")
    g.add_big(a["generate"], "Generate")
    g.add_big(a["execute"], "Run", name="ribbon_run")
    g.add_big(a["kill"], "Stop")

    g = page.add_group("Analysis")
    g.add_big(a["errors"], "Errors")
    g.add_big(a["properties"], "Properties")

    # --- Block -----------------------------------------------------------
    page = ribbon.add_page("Block")
    g = page.add_group("State")
    g.add_big(a["enable"], "Enable")
    g.add_big(a["disable"], "Disable")
    g.add_big(a["bypass"], "Bypass")

    g = page.add_group("Orientation")
    g.add_big(a["rotate_ccw"], "Rotate Left")
    g.add_big(a["rotate_cw"], "Rotate Right")

    g = page.add_group("Ports")
    g.add_column([(a["block_inc_type"], "Next Type"), (a["block_dec_type"], "Previous Type"),
                  (a["autoconnect"], "Autoconnect")])
    g.add_column([(a["toggle_source_bus"], "Bus Outputs"), (a["toggle_sink_bus"], "Bus Inputs")])

    g = page.add_group("Hierarchy")
    g.add_big(a["create_hier"], "Create Hier")
    g.add_big(a["open_hier"], "Open Hier")

    g = page.add_group("Edit")
    g.add_big(a["properties"], "Properties")

    # --- Simulation ------------------------------------------------------
    page = ribbon.add_page("Simulation")
    g = page.add_group("Prepare")
    g.add_big(a["errors"], "Errors")
    g.add_big(a["generate"], "Generate")
    g.add_big(a["reload"], "Reload Blocks")

    g = page.add_group("Execute")
    g.add_big(a["execute"], "Run", name="ribbon_run")
    g.add_big(a["kill"], "Stop")

    g = page.add_group("Profiler")
    g.add_column([(a["start_profiler"], "Start Profiler"), (a["stop_profiler"], "Stop Profiler")])

    # --- View ------------------------------------------------------------
    page = ribbon.add_page("View")
    g = page.add_group("Zoom")
    g.add_big(a["zoom_in"], "Zoom In")
    g.add_big(a["zoom_out"], "Zoom Out")
    g.add_big(a["zoom_original"], "Reset Zoom")

    g = page.add_group("Align")
    g.add_column([(a["vertical_align_top"], "Top"), (a["vertical_align_middle"], "Middle"),
                  (a["vertical_align_bottom"], "Bottom")])
    g.add_column([(a["horizontal_align_left"], "Left"), (a["horizontal_align_center"], "Center"),
                  (a["horizontal_align_right"], "Right")])

    g = page.add_group("Canvas")
    g.add_big(a["toggle_grid"], "Grid")
    g.add_big(a["view_undo_stack"], "History")

    # --- Tools -----------------------------------------------------------
    page = ribbon.add_page("Tools")
    g = page.add_group("Explore")
    g.add_big(a["example_browser"], "Examples")
    g.add_big(a["module_browser"], "OOT Modules")
    g.add_big(a["filter_design_tool"], "Filter Design")

    g = page.add_group("Settings")
    g.add_big(a["preferences"], "Preferences")

    g = page.add_group("Help")
    g.add_big(a["help"], "Help")
    g.add_column([(a["types"], "Types"), (a["keys"], "Shortcuts"), (a["guided_tutorials"], "Tutorials")])

    return ribbon
