import sys
import os
import builtins
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(os.environ.get("GRC_UI_OUT", os.path.join(HERE, "out")))
os.environ["GRC_UI_OUT"] = OUT
os.makedirs(os.path.join(OUT, "conf"), exist_ok=True)
sys.path[:0] = [os.path.join(HERE, "stub"), os.path.abspath(os.path.join(HERE, "..", ".."))]
from grc import main as m
conf = os.path.join(OUT, "conf", "grc_qt.conf")


def run(argv, config=None, block_pyqt=False):
    calls = []
    m.run_qt = lambda a, l: calls.append("qt")
    m.run_gtk = lambda a, l: calls.append("gtk")
    with open(conf, "w") as f:
        f.write("[grc]\ndefault_grc=%s\n" % config if config else "[appearance]\ntheme=modern\n")
    real_import = builtins.__import__

    def fake(name, *a, **k):
        if block_pyqt and name == "PyQt6.QtWidgets":
            raise ImportError("no PyQt6")
        return real_import(name, *a, **k)
    builtins.__import__ = fake
    sys.argv = ["gnuradio-companion"] + argv
    try:
        m.main()
    finally:
        builtins.__import__ = real_import
    return calls


cases = [([], None, False, ["qt"]), ([], "grc_qt", False, ["qt"]), ([], "grc_gtk", False, ["gtk"]),
         (["--gtk"], None, False, ["gtk"]), (["--qt"], "grc_gtk", False, ["qt"]), ([], None, True, ["gtk"])]
ok = True
for argv, cfg, block, want in cases:
    got = run(argv, cfg, block)
    print("PASS" if got == want else "FAIL", argv, cfg, "no-PyQt6" if block else "", got)
    ok &= got == want
with open(conf, "w") as f:
    f.write("[appearance]\ntheme=modern\n")
sys.exit(0 if ok else 1)
