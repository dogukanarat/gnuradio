import os
import sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
files = sys.argv[1:]
sys.argv = [sys.argv[0]] + files
src = open(os.path.join(HERE, "run_grc.py")).read().split("app.MainWindow.resize")[0]
ns = {"__file__": os.path.join(HERE, "run_grc.py"), "__name__": "ov"}
exec(compile(src, "run_grc.py", "exec"), ns)
import overlap_lib
app = ns["app"]
w = app.MainWindow
w.show()
app.processEvents()
total = 0
for i in range(w.tabWidget.count()):
    view = w.tabWidget.widget(i)
    found = overlap_lib.overlaps(view.scene().core)
    total += len(found)
    print(w.tabWidget.tabText(i), len(view.scene().core.connections), "connections,", len(found), "overlaps")
    for f in found:
        print("   ", f)
sys.exit(1 if total else 0)
