"""Open the properties dialog of some blocks and save screenshots."""
import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
prefix = sys.argv[1]
names = sys.argv[2].split(",")
sys.argv = [sys.argv[0]] + sys.argv[3:]
src = open(os.path.join(HERE, "run_grc.py")).read().split("app.MainWindow.resize")[0]
ns = {"__file__": os.path.join(HERE, "run_grc.py"), "__name__": "p"}
exec(compile(src, "run_grc.py", "exec"), ns)
app = ns["app"]
w = app.MainWindow
w.resize(1500, 920)
w.show()
app.processEvents()
blocks = {b.name: b for b in w.currentFlowgraph.blocks}
tab = int(os.environ.get("PROPS_TAB", "0"))
for n in names:
    if n.startswith("new:"):
        before = set(blocks)
        w.currentFlowgraphScene.add_block(n[4:], (900, 650))
        app.processEvents()
        blocks = {b.name: b for b in w.currentFlowgraph.blocks}
        n = [k for k in blocks if k not in before][0]
    b = blocks[n]
    b.gui.open_properties()
    d = b.gui.props_dialog
    d.resize(int(os.environ.get("PROPS_W", "700")), int(os.environ.get("PROPS_H", "520")))
    d.tabs.setCurrentIndex(min(tab, d.tabs.count() - 1))
    app.processEvents()
    app.processEvents()
    path = os.path.join(os.environ["GRC_UI_OUT"], f"{prefix}_{n}.png")
    d.grab().save(path)
    print("saved", path, [d.tabs.tabText(i) for i in range(d.tabs.count())])
    d.reject()
