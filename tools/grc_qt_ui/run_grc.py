"""Dev harness: run the GRC Qt frontend from the source tree without an
installed GNU Radio, optionally save a screenshot and quit.

usage: python3 run_grc.py [out.png] [flowgraph.grc ...]

Environment:
  GRC_THEME        modern (default), light or dark
  GRC_UI_OUT       directory for settings, caches and screenshots (default: ./out)
  GRC_REPO         source tree to run (default: the tree this file is in)
  GRC_SELECT       comma separated block names to select before the screenshot
  GRC_TAB          ribbon tab index to show
  GRC_ZOOM, GRC_CX, GRC_CY   zoom the view and centre it on a scene point
  GRC_RENDER       "x,y,w,h": render that scene rectangle instead of the window
  GRC_RENDER_SCALE scale of GRC_RENDER (default 2)
"""
import os
import sys
import glob
import gettext
import logging
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("GRC_REPO", os.path.abspath(os.path.join(HERE, "..", "..")))
OUT = os.path.abspath(os.environ.get("GRC_UI_OUT", os.path.join(HERE, "out")))
os.environ["GRC_UI_OUT"] = OUT  # read by the gnuradio stub
for sub in ("conf", "cache", "persist", "userconf"):
    os.makedirs(os.path.join(OUT, sub), exist_ok=True)
# A fresh GRC settings file for every run: the theme, nothing else remembered
with open(os.path.join(OUT, "conf", "grc_qt.conf"), "w") as conf:
    conf.write("[appearance]\ntheme={}\n".format(os.environ.get("GRC_THEME", "modern")))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(HERE, "stub"))

# Collect block yml dirs from the source tree
dirs = {os.path.join(REPO, "grc", "blocks")}
for f in glob.glob(os.path.join(REPO, "gr-*", "grc", "*.yml")):
    dirs.add(os.path.dirname(f))
os.environ["GRC_BLOCKS_PATH"] = os.pathsep.join(sorted(dirs))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("XDG_CONFIG_HOME", os.path.join(OUT, "cfg"))
os.environ.setdefault("XDG_STATE_HOME", os.path.join(OUT, "state"))

logging.basicConfig(level=logging.WARNING)

from grc.gui_qt import properties  # noqa: E402
from grc.gui_qt.grc import Application  # noqa: E402
from grc.gui_qt.Platform import Platform  # noqa: E402
from PyQt6.QtCore import QTimer  # noqa: E402

args = sys.argv[1:]
out = args.pop(0) if args and args[0].endswith(".png") else None

settings = properties.Properties([""])
lang = gettext.translation(settings.APP_NAME, settings.path.LANGUAGE,
                           languages=settings.DEFAULT_LANGUAGE, fallback=True)
lang.install()

model = Platform(version="3.10-dev", version_parts=("3", "10", "0"),
                 prefs=None, install_prefix=tempfile.gettempdir())
model.build_library()
app = Application(settings, model, args)
app.MainWindow.resize(1500, 920)
app.MainWindow.show()

if out:
    def snap():
        sel = os.environ.get("GRC_SELECT")
        if sel:
            for b in app.MainWindow.currentFlowgraph.blocks:
                if b.name in sel.split(","):
                    b.gui.setSelected(True)
        tab = os.environ.get("GRC_TAB")
        if tab and getattr(app.MainWindow, "ribbon_toolbar", None):
            app.MainWindow.ribbon_toolbar.ribbon.setCurrentIndex(int(tab))
        z = float(os.environ.get("GRC_ZOOM", "0"))
        if z:
            v = app.MainWindow.currentView
            v.zoom(z)
            v.centerOn(float(os.environ.get("GRC_CX", "600")), float(os.environ.get("GRC_CY", "330")))
            app.processEvents()
        region = os.environ.get("GRC_RENDER")
        if region:
            from PyQt6.QtGui import QImage, QPainter
            from PyQt6.QtCore import QRectF
            x, y, rw, rh = (float(v) for v in region.split(","))
            scale = float(os.environ.get("GRC_RENDER_SCALE", "2"))
            img = QImage(int(rw * scale), int(rh * scale), QImage.Format.Format_ARGB32)
            img.fill(0xFFFFFFFF)
            p = QPainter(img)
            v = app.MainWindow.currentView
            v.drawBackground(p, QRectF(0, 0, img.width(), img.height())) if False else None
            v.scene().render(p, QRectF(0, 0, img.width(), img.height()), QRectF(x, y, rw, rh))
            p.end()
            img.save(out)
        else:
            app.MainWindow.grab().save(out)
        print("saved", out)
        app.quit()
    QTimer.singleShot(1500, snap)
sys.exit(app.exec())
