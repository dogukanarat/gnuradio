"""Minimal stand-in for gnuradio.gr so GRC's Qt GUI can run from source."""
import os
import tempfile


class _Prefs:
    def get_string(self, section, key, default):
        return str(default)

    def get_bool(self, section, key, default):
        return default

    def set_string(self, *a):
        pass


def prefs():
    return _Prefs()


def userconf_path():
    return os.path.join(os.environ.get("GRC_UI_OUT", tempfile.gettempdir()), "userconf")


def version():
    return "3.10-dev"


def prefix():
    return tempfile.gettempdir()
