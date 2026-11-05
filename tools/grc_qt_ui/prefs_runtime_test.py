import os
import sys
import tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
custom = sys.argv[1] if len(sys.argv) > 1 else ""
out = sys.argv[2]
sys.argv = [sys.argv[0], os.path.join(HERE, "routing.grc")]
conf_dir = os.path.join(os.path.abspath(os.environ.get("GRC_UI_OUT", os.path.join(HERE, "out"))), "userconf")
os.makedirs(conf_dir, exist_ok=True)
conf = os.path.join(conf_dir, "config.conf")
if custom:
    open(conf, "w").write(f"[qtgui]\nqss={custom}\n")
elif os.path.exists(conf):
    os.remove(conf)
src = open(os.path.join(HERE, "run_grc.py")).read().split("app.MainWindow.resize")[0]
ns = {"__file__": os.path.join(HERE, "run_grc.py"), "__name__": "p"}
exec(compile(src, "run_grc.py", "exec"), ns)
from grc.gui_qt.components.preferences import PreferencesDialog
from PyQt6.QtWidgets import QComboBox, QLabel
app = ns["app"]
d = PreferencesDialog(app.qsettings)
d.resize(760, 640)
d.tab_widget.setCurrentIndex(d.tab_widget.count() - 1)
d.show()
app.processEvents()
combo = None
for label in d.findChildren(QLabel):
    if label.text().startswith("Plot theme"):
        combo = [c for c in d.findChildren(QComboBox) if c.toolTip() == label.toolTip()][0]
print("tab:", d.tab_widget.tabText(d.tab_widget.currentIndex()), "| shown:", combo.currentText(),
      "| options:", [combo.itemText(i) for i in range(combo.count())])
d.grab().save(out)
# save with a different choice and read it back
pick = int(os.environ.get("PICK", "1"))
combo.setCurrentIndex(pick)
d.accept()
d.save_all()
print("saved value:", open(conf).read().split("[qtgui]")[1].strip().splitlines()[0])
