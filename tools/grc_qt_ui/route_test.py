import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0], os.path.join(HERE, "routing.grc")]
src = open(os.path.join(HERE, "run_grc.py")).read().split("app.MainWindow.resize")[0]
ns = {"__file__": os.path.join(HERE, "run_grc.py"), "__name__": "rt"}
exec(compile(src, "run_grc.py", "exec"), ns)
app = ns["app"]
w = app.MainWindow
w.resize(1500, 920)
w.show()
app.processEvents()
from PyQt6.QtCore import QRectF
scene = w.currentFlowgraphScene
fg = w.currentFlowgraph
B = {b.name: b for b in fg.blocks}
res = []


def check(n, c):
    res.append(bool(c))
    print(("PASS " if c else "FAIL ") + n)


def points(g):
    return [(g._line.elementAt(i).x, g._line.elementAt(i).y) for i in range(g._line.elementCount())]


def crossings():
    bad = []
    for c in fg.connections:
        pts = points(c.gui)
        for b in fg.blocks:
            if b in (c.source_block, c.sink_block) or b.key in ("options", "variable"):
                continue
            r = b.gui.mapRectToScene(QRectF(0, 0, b.gui.width, b.gui.height))
            for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
                if abs(y1 - y2) < .01 and r.top() < y1 < r.bottom() and min(x1, x2) < r.right() and max(x1, x2) > r.left():
                    bad.append((c.source_block.name, c.sink_block.name, b.name))
                if abs(x1 - x2) < .01 and r.left() < x1 < r.right() and min(y1, y2) < r.bottom() and max(y1, y2) > r.top():
                    bad.append((c.source_block.name, c.sink_block.name, b.name))
    return bad


def orthogonal():
    return all(abs(x1 - x2) < .01 or abs(y1 - y2) < .01
               for c in fg.connections for (x1, y1), (x2, y2) in zip(points(c.gui), points(c.gui)[1:]))


check("all routes orthogonal", orthogonal())
check("no line runs through a block", not crossings())
src_port = B["blocks_throttle2_0"].sources[0].gui
check("connected output hides its arrow", not src_port._draws_body())
check("line starts on block border",
      abs(src_port.connection_point.x() - (B["blocks_throttle2_0"].gui.x() + B["blocks_throttle2_0"].gui.width)) < 0.5)
fb = [c for c in fg.connections if c.sink_block.name == "blocks_delay_0"][0]
ys = [p[1] for p in points(fb.gui)]
mul_bottom = B["blocks_multiply_const_vxx_0"].gui.sceneBoundingRect().bottom()
delay_top = B["blocks_delay_0"].gui.sceneBoundingRect().top()
check("feedback runs through the gap between blocks", any(mul_bottom < y < delay_top for y in ys))
check("feedback branch has a dot", not fb.gui._branch_dot.isEmpty())

# Drag Throttle onto the line Signal Source -> Freq Sink and release: line must move away
thr = B["blocks_throttle2_0"].gui
line = [c for c in fg.connections if c.source_block.name == "analog_sig_source_x_0" and c.sink_block.name == "qtgui_freq_sink_x_0"][0]
y_line = points(line.gui)[-1][1]
thr.setPos(500, y_line - thr.height / 2)
scene.refresh_connections()
check("line re-routed around moved block", not any(t[2] == "blocks_throttle2_0" for t in crossings()))
check("still orthogonal after move", orthogonal())
print(f"{sum(res)}/{len(res)} passed")
sys.exit(0 if all(res) else 1)
