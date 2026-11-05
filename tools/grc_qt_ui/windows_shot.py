"""Open every secondary window, dialog and menu of the Qt GUI and save screenshots.

usage: python3 windows_shot.py <prefix> <flowgraph.grc>
"""
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
prefix = sys.argv[1]
sys.argv = [sys.argv[0]] + sys.argv[2:]
# give the example browser something to index
os.environ["GRC_EXAMPLES_DIR"] = os.path.abspath(os.path.join(HERE, "..", "..", "gr-blocks", "examples"))
src = open(os.path.join(HERE, "run_grc.py")).read().split("app.MainWindow.resize")[0]
ns = {"__file__": os.path.join(HERE, "run_grc.py"), "__name__": "w"}
exec(compile(src, "run_grc.py", "exec"), ns)

from PyQt6.QtCore import QPoint, QPointF, QTimer, Qt  # noqa: E402
from PyQt6.QtGui import QContextMenuEvent  # noqa: E402
from PyQt6.QtWidgets import QApplication, QDialog, QMenu, QMessageBox, QWidget  # noqa: E402

app = ns["app"]
w = app.MainWindow
w.resize(1500, 920)
w.show()
app.processEvents()
outdir = os.path.join(os.environ["GRC_UI_OUT"], "windows")
os.makedirs(outdir, exist_ok=True)
done = []


def save(widget, name):
    path = os.path.join(outdir, f"{prefix}_{name}.png")
    widget.grab().save(path)
    done.append(name)
    print("saved", name, widget.__class__.__name__, widget.size().width(), "x", widget.size().height())


def top_window(exclude):
    """The newest visible popup / modal / top level window that is not in `exclude`."""
    for getter in (app.activePopupWidget, app.activeModalWidget):
        widget = getter()
        if widget is not None and widget not in exclude:
            return widget
    for widget in reversed(app.topLevelWidgets()):
        if widget.isVisible() and widget not in exclude and widget is not w and isinstance(widget, (QDialog, QMenu, QWidget)):
            if widget.windowType() in (Qt.WindowType.Dialog, Qt.WindowType.Popup, Qt.WindowType.Window):
                return widget
    return None


def capture(name, trigger, size=None, prepare=None):
    """Run `trigger` (which may block in exec()), grab the window it opens and close it."""
    before = {x for x in app.topLevelWidgets() if x.isVisible()}

    def grab_and_close():
        widget = top_window(before)
        if widget is None:
            print("NO WINDOW", name)
            return
        if size:
            widget.resize(*size)
        if prepare:
            prepare(widget)
        app.processEvents()
        save(widget, name)
        if isinstance(widget, QDialog):
            widget.reject()
        widget.close()

    QTimer.singleShot(700, grab_and_close)
    trigger()
    # non-blocking windows: let the timer fire
    end = time.time() + 1.5
    while time.time() < end:
        app.processEvents()
        time.sleep(0.02)


scene = w.currentFlowgraphScene
view = w.currentView
blocks = {b.name: b for b in w.currentFlowgraph.blocks}

# ---------------------------------------------------------------- dialogs
capture("preferences", lambda: w.actions["preferences"].trigger(), size=(760, 560))
capture("errors", w.errors_triggered, size=(760, 460))
capture("oot_browser", w.module_browser_triggered, size=(900, 560))
capture("undo_history", w.view_undo_stack_triggered, size=(320, 300))

# example browser needs the background indexer to finish
end = time.time() + 30
while not w.examples_found and time.time() < end:
    app.processEvents()
    time.sleep(0.05)
print("examples indexed:", w.examples_found)


def pick_example(dialog):
    from PyQt6.QtWidgets import QTreeView, QTreeWidget
    for tree in dialog.findChildren(QTreeView):
        tree.expandAll()
        model = tree.model()

        def leaf(parent):
            for r in range(model.rowCount(parent)):
                idx = model.index(r, 0, parent)
                if model.rowCount(idx) == 0 and r > 0:
                    return idx
                found = leaf(idx)
                if found is not None:
                    return found
            return None
        idx = leaf(tree.rootIndex())
        if idx is not None:
            tree.setCurrentIndex(idx)
            tree.clicked.emit(idx)
            if isinstance(tree, QTreeWidget):
                tree.itemClicked.emit(tree.currentItem(), 0)
            return


capture("example_browser", w.example_browser_triggered, size=(1000, 620), prepare=pick_example)
capture("no_examples_box", lambda: w.example_browser_triggered(key_filter="blocks_null_sink_does_not_exist"))

# ---------------------------------------------------------- message boxes
capture("about", w.about_triggered)
capture("about_qt", w.about_qt_triggered)
capture("get_involved", w.get_involved_triggered)
capture("help", w.help_triggered)
capture("types", w.types_triggered)
capture("keys", w.keys_triggered)


def unsaved_close():
    scene.set_saved(False)
    w.close_triggered(w.tabWidget.currentIndex())


capture("unsaved_changes", unsaved_close)

# ----------------------------------------------------------- file dialogs
capture("open_file", lambda: w.actions["open"].trigger(), size=(860, 520))
capture("save_as", w.save_as_triggered, size=(860, 520))

# ----------------------------------------------------------------- menus
for key in ("file", "edit", "view", "build", "tools", "help"):
    menu = w.menus[key]
    capture(f"menu_{key}", lambda m=menu: m.popup(w.mapToGlobal(QPoint(40, 30))))

# block right-click menu
blk = next(b for b in w.currentFlowgraph.blocks if b.key != "options" and b.sources)
scene.clearSelection()
blk.gui.setSelected(True)
capture("menu_block", lambda: blk.gui.context_menu(w.mapToGlobal(QPoint(600, 400))))
# empty canvas right-click
scene.clearSelection()
capture("menu_canvas", lambda: view.contextMenuEvent(
    QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(50, 50), view.mapToGlobal(QPoint(50, 50)))))

# block library: search, then right-click a block
lib = app.BlockLibrary
from PyQt6.QtTest import QTest  # noqa: E402
lib._search_bar.setFocus()
QTest.keyClicks(lib._search_bar, "low pass")
app.processEvents()
popup = lib._search_bar.completer().popup()
if popup.isVisible():
    save(popup, "block_search_popup")
    popup.hide()
save(lib, "block_library_search")
lib._search_bar.clear()
app.processEvents()

# console with some output
import logging  # noqa: E402
logging.getLogger("grc").setLevel(logging.DEBUG)  # as grc/main.py does
log = logging.getLogger("grc.application")
log.info("Generating: '/home/user/sine_noise.py'")
log.info("Executing: /usr/bin/python3 -u /home/user/sine_noise.py")
log.warning("Example warning message")
log.error("Example error message")
app.processEvents()
save(app.Console, "console")
save(app.VariableEditor, "variable_editor")

var_tree = app.VariableEditor._tree
capture("menu_variable_editor", lambda: app.VariableEditor.contextMenuEvent(
    QContextMenuEvent(QContextMenuEvent.Reason.Mouse, QPoint(40, 40), var_tree.mapToGlobal(QPoint(40, 40)))))

print("done:", len(done))
