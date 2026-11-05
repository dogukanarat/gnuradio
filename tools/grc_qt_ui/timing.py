import os
import sys
import time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0]] + sys.argv[1:]
src = open(os.path.join(HERE, "run_grc.py")).read().split("app.MainWindow.resize")[0]
ns = {"__file__": os.path.join(HERE, "run_grc.py"), "__name__": "t"}
exec(compile(src, "run_grc.py", "exec"), ns)
app = ns["app"]
w = app.MainWindow
for i in range(w.tabWidget.count()):
    sc = w.tabWidget.widget(i).scene()
    t = time.time()
    sc.refresh_connections()
    dt = time.time() - t
    # simulate a drag step: update connections of one block (fast mode)
    b = sc.core.blocks[len(sc.core.blocks) // 2]
    sc.moving_blocks = True
    t2 = time.time()
    b.gui.moveBy(5, 5)
    d2 = time.time() - t2
    sc.moving_blocks = False
    print(w.tabWidget.tabText(i), len(sc.core.connections), f"refresh {dt * 1000:.0f} ms, drag step {d2 * 1000:.1f} ms")
