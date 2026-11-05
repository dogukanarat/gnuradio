"""Scripted smoke test of the modernised Qt GUI (run like run_grc.py)."""
import os
import sys
import runpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0], os.path.join(HERE, "sine_noise.grc")]

# Reuse run_grc's setup but stop before the event loop
src = open(os.path.join(HERE, "run_grc.py")).read().split("app.MainWindow.resize")[0]
ns = {"__file__": os.path.join(HERE, "run_grc.py"), "__name__": "smoke"}
exec(compile(src, "run_grc.py", "exec"), ns)
app = ns["app"]
w = app.MainWindow
w.resize(1500, 920)
w.show()
app.processEvents()

from PyQt6.QtCore import QPointF  # noqa: E402

scene = w.currentFlowgraphScene
fg = w.currentFlowgraph
blocks = {b.name: b for b in fg.blocks}
results = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name)


# 1. Ports: hidden-name arrow ports and connection points
thr = blocks["blocks_throttle2_0"]
sink = thr.sinks[0].gui
src = thr.sources[0].gui
check("unlabelled port is an arrow", not sink.show_name and sink.width == 10.0)
check("connected sink hides its arrow", not sink._draws_body())
n_before = len(fg.blocks)
scene.add_block("blocks_null_sink", (900, 600))
new_block = [b for b in fg.blocks if b.name not in blocks][0]
check("block added", len(fg.blocks) == n_before + 1)
check("unconnected sink shows its arrow", new_block.sinks[0].gui._draws_body())
w.undo_triggered()
check("add undone", len(fg.blocks) == n_before)
cp = sink.connection_point
check("sink connection point left of block", cp.x() < thr.gui.x())
check("source connection point right of block", src.connection_point.x() >= thr.gui.x() + thr.gui.width)

# 2. Branch dot on the multiply const output (2 sinks)
mul = blocks["blocks_multiply_const_vxx_0"]
conns = list(mul.sources[0].connections())
check("two connections leave the gain", len(conns) == 2)
check("branch dot drawn", all(not c.gui._branch_dot.isEmpty() for c in conns))
bends = {round(c.gui._line.elementAt(1).x, 2) for c in conns}
check("connections share one trunk", len(bends) == 1)
check("gain block shape", mul.gui.shape_kind == "gain")
check("add block shape", blocks["blocks_add_xx_0"].gui.shape_kind == "op")

# 3. Move a block -> connection follows
before = conns[0].gui.path().boundingRect()
mul.gui.setSelected(True)
mul.gui.moveBy(0, 40)
app.processEvents()
after = conns[0].gui.path().boundingRect()
check("connection follows moved block", before != after)
mul.gui.moveBy(0, -40)

# 4. Rotate a block: connections re-route, no exceptions
scene.clearSelection()
thr.gui.setSelected(True)
w.rotate_cw_triggered()
app.processEvents()
check("rotated block", thr.gui.rotation() in (90.0, 270.0))
path = list(thr.sources[0].connections())[0].gui._line
check("rotated route is orthogonal", all(
    abs(path.elementAt(i).x - path.elementAt(i - 1).x) < 0.01 or abs(path.elementAt(i).y - path.elementAt(i - 1).y) < 0.01
    for i in range(1, path.elementCount())))
w.undo_triggered()
app.processEvents()
check("rotation undone", thr.gui.rotation() == 0.0)

# 5. Align top + undo
scene.clearSelection()
a, b = blocks["qtgui_time_sink_x_0"], blocks["qtgui_freq_sink_x_0"]
a.gui.setSelected(True)
b.gui.setSelected(True)
w.updateActions()
check("align enabled for 2 blocks", w.actions["vertical_align_top"].isEnabled())
ya, yb = a.gui.y(), b.gui.y()
w.vertical_align_top_triggered()
check("aligned top", abs(a.gui.y() - b.gui.y()) < 0.5)
w.undo_triggered()
check("align undone", abs(a.gui.y() - ya) < 0.5 and abs(b.gui.y() - yb) < 0.5)
scene.clearSelection()
w.updateActions()
check("align disabled without selection", not w.actions["vertical_align_top"].isEnabled())

# 6. Grid toggle and status bar
w.actions["toggle_grid"].trigger()
check("grid hidden", not w.currentView.show_grid)
w.actions["toggle_grid"].trigger()
check("grid shown", w.currentView.show_grid)
check("status counts", w.status_counts.text() == "8 blocks · 6 connections")
w.zoom_in_triggered()
check("status zoom updates", w.status_zoom.text() != "100 %")

# 7. Ribbon mirrors action state
from grc.gui_qt.components.ribbon import RibbonButton  # noqa: E402
buttons = w.ribbon_toolbar.findChildren(RibbonButton)
paste = [x for x in buttons if x.text() == "Paste"][0]
check("ribbon paste disabled with empty clipboard", not paste.isEnabled())
w.actions["paste"].setEnabled(True)
check("ribbon follows action enable", paste.isEnabled())

failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
sys.exit(1 if failed else 0)
