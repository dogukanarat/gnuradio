import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0], os.path.join(HERE, "train_rot.grc")]
src = open(os.path.join(HERE, "run_grc.py")).read().split("app.MainWindow.resize")[0]
ns = {"__file__": os.path.join(HERE, "run_grc.py"), "__name__": "c"}
exec(compile(src, "run_grc.py", "exec"), ns)
app = ns["app"]
w = app.MainWindow
w.resize(1500, 920)
w.show()
app.processEvents()
from PyQt6.QtCore import QPointF
scene = w.currentFlowgraphScene
fg = w.currentFlowgraph
B = {b.name: b for b in fg.blocks}
res = []


def check(n, c):
    res.append(bool(c))
    print(("PASS " if c else "FAIL ") + n)


def dir_of(port):
    d = port.gui.direction
    return (round(d.x()), round(d.y()))


def last_dir(conn):
    pts = conn.gui._points
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    return ((x2 > x1) - (x2 < x1), (y2 > y1) - (y2 < y1))


def touch_point(port):
    # where the arrow tip ends: connection point + direction * arrow length
    from grc.gui_qt.Constants import CONNECTOR_ARROW_HEIGHT
    return port.gui.connection_point + port.gui.direction * CONNECTOR_ARROW_HEIGHT


def check_circle(block, label):
    g = block.gui
    c = g.mapToScene(QPointF(g.width / 2, g.height / 2))
    r = g.width / 2
    want = {1: [(1, 0)], 2: [(1, 0), (0, -1)], 3: [(0, 1), (1, 0), (0, -1)]}[len(block.sinks)]
    rot = int(g.rotation()) % 360

    def rotv(v):
        x, y = v
        for _ in range(rot // 90):
            x, y = -y, x
        return (x, y)
    check(f"{label}: inputs point at the centre from 90/180/270", [dir_of(p) for p in block.sinks] == [rotv(v) for v in want])
    for p in block.sinks:
        t = touch_point(p)
        dist = ((t.x() - c.x()) ** 2 + (t.y() - c.y()) ** 2) ** 0.5
        check(f"{label}: {p.key} arrow tip on the circle (dist {dist:.1f}, r {r:.1f})", abs(dist - r) < 1.0)
        for conn in p.connections():
            check(f"{label}: {p.key} line enters straight ({last_dir(conn)})", last_dir(conn) == dir_of(p))
    out = block.sources[0]
    o = out.gui.connection_point
    check(f"{label}: output on the circle at 0 deg", abs(((o.x() - c.x()) ** 2 + (o.y() - c.y()) ** 2) ** 0.5 - r) < 1.0 and
          dir_of(out) == rotv((1, 0)))


check("Sum1 is a circle", B["Sum1"].gui.shape_kind == "op")
check_circle(B["Sum1"], "Sum1 (3 in)")
check_circle(B["Sum2"], "Sum2 (2 in)")
check_circle(B["Subtract"], "Subtract (rotated 180)")

# rotate a circle by 90 and check again
scene.clearSelection()
B["Sum2"].gui.setSelected(True)
w.rotate_cw_triggered()
scene.refresh_connections()
app.processEvents()
check_circle(B["Sum2"], "Sum2 rotated")
w.undo_triggered()
scene.refresh_connections()

# more than 3 inputs -> box
dlg_block = B["Sum1"]
dlg_block.params["num_inputs"].set_value("4")
dlg_block.rewrite()
dlg_block.gui.create_shapes_and_labels()
check("4 inputs: drawn as a box", dlg_block.gui.shape_kind is None)
check("4 inputs: ports unrotated on the left", all(int(p.gui.rotation()) == 0 for p in dlg_block.sinks))
dlg_block.params["num_inputs"].set_value("3")
dlg_block.rewrite()
dlg_block.gui.create_shapes_and_labels()
check("3 inputs again: circle", dlg_block.gui.shape_kind == "op")

# properties dialog: edit a value and accept
g = B["Gain"]
g.gui.open_properties()
d = g.gui.props_dialog
app.processEvents()
edits = [e for e in d.edit_params if getattr(e, "param", None) is g.params["const"]]
check("dialog has the Constant editor", len(edits) == 1)
edits[0].setText("2/M1")
d.accept()
app.processEvents()
check("accepted value stored", g.params["const"].value == "2/M1")
g.gui.open_properties()
d = g.gui.props_dialog
[e for e in d.edit_params if getattr(e, "param", None) is g.params["const"]][0].setText("99")
d.reject()
check("cancel restores the value", g.params["const"].value == "2/M1")
g.gui.open_properties()
d = g.gui.props_dialog
from PyQt6.QtWidgets import QLabel
title = d.findChild(QLabel, "props_title")
check("header shows block name", title is not None and title.text() == g.label)
d.reject()
print(f"{sum(res)}/{len(res)} passed")
sys.exit(0 if all(res) else 1)
