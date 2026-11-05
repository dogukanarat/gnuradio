"""Stand-in for gnuradio.gr.paths: everything lives in $GRC_UI_OUT."""
import os
import tempfile


def _out(sub):
    path = os.path.join(os.environ.get("GRC_UI_OUT", tempfile.gettempdir()), sub)
    os.makedirs(path, exist_ok=True)
    return path


def userconf():
    return _out("conf")


def cache():
    return _out("cache")


def persistent():
    return _out("persist")
