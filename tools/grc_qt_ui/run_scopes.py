"""Run a generated QT GUI flowgraph, screenshot its window after a few seconds."""
import importlib.util
import sys

gen_file, out, seconds = sys.argv[1], sys.argv[2], float(sys.argv[3])
qss = sys.argv[4] if len(sys.argv) > 4 else None
from PyQt5 import Qt  # noqa: E402

spec = importlib.util.spec_from_file_location("fg", gen_file)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
cls = [v for k, v in vars(mod).items() if isinstance(v, type) and hasattr(v, "start") and hasattr(v, "show")][0]

app = Qt.QApplication(sys.argv[:1])
if qss:
    app.setStyleSheet(open(qss).read())
tb = cls()
tb.start()
tb.resize(int(sys.argv[5]) if len(sys.argv) > 5 else 1200, int(sys.argv[6]) if len(sys.argv) > 6 else 900)
tb.show()


def snap():
    tb.grab().save(out)
    print("saved", out)
    tb.stop()
    tb.wait()
    app.quit()


Qt.QTimer.singleShot(int(seconds * 1000), snap)
app.exec_()
