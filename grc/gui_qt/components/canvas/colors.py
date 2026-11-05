# TODO: This file is a modified copy of the old gui/Platform.py
"""
Copyright 2008,2013 Free Software Foundation, Inc.
This file is part of GNU Radio
SPDX-License-Identifier: GPL-2.0-or-later
"""


from PyQt6.QtGui import QColor

from ... import Constants


def get_color(rgb):
    color = QColor(rgb)
    return color


#################################################################################
# Canvas palettes
#
# The canvas items read the module level names below at paint time, so
# set_theme() can swap the whole palette by rebinding them.
#################################################################################
_PALETTES = {
    # Light engineering look: white canvas, slate outlines, blue accent.
    "modern": {
        "HIGHLIGHT_COLOR": "#1660C9",
        "BORDER_COLOR": "#2A3441",
        "BORDER_COLOR_DISABLED": "#A3ACB8",
        "FONT_COLOR": "#1D2733",
        "PARAM_NAME_COLOR": "#6B7686",
        "PARAM_VALUE_COLOR": "#1D2733",
        "ERROR_FONT_COLOR": "#C62828",
        "COMMENT_COLOR": "#5B6676",
        "COMMENT_COLOR_DISABLED": "#9AA3AF",
        "BLOCK_DEPRECATED_BACKGROUND_COLOR": "#FFF4D6",
        "BLOCK_DEPRECATED_BORDER_COLOR": "#D9822B",
        "MISSING_BLOCK_BACKGROUND_COLOR": "#FFF1F1",
        "MISSING_BLOCK_BORDER_COLOR": "#D32F2F",
        "BLOCK_ENABLED_COLOR": "#FFFFFF",
        "BLOCK_DISABLED_COLOR": "#EEF0F3",
        "BLOCK_BYPASSED_COLOR": "#E4ECF7",
        "BLOCK_SHADOW_COLOR": "#1C142030",
        "CONNECTION_ENABLED_COLOR": "#2A3441",
        "CONNECTION_DISABLED_COLOR": "#B9C1CC",
        "CONNECTION_ERROR_COLOR": "#D32F2F",
        "FLOWGRAPH_BACKGROUND_COLOR": "#FFFFFF",
        "GRID_MINOR_COLOR": "#EBEFF4",
        "GRID_MAJOR_COLOR": "#D9E0E8",
        "VARIABLE_BACKGROUND_COLOR": "#F4F7FA",
        "VARIABLE_BORDER_COLOR": "#9AA6B5",
    },
    # Dark counterpart of the modern look.
    "dark": {
        "HIGHLIGHT_COLOR": "#5AA2FF",
        "BORDER_COLOR": "#8A96A8",
        "BORDER_COLOR_DISABLED": "#4A5361",
        "FONT_COLOR": "#E3E8EF",
        "PARAM_NAME_COLOR": "#8F9AAB",
        "PARAM_VALUE_COLOR": "#E3E8EF",
        "ERROR_FONT_COLOR": "#FF6B6B",
        "COMMENT_COLOR": "#A9B3C1",
        "COMMENT_COLOR_DISABLED": "#6B7480",
        "BLOCK_DEPRECATED_BACKGROUND_COLOR": "#3A3122",
        "BLOCK_DEPRECATED_BORDER_COLOR": "#E59A3A",
        "MISSING_BLOCK_BACKGROUND_COLOR": "#3A2326",
        "MISSING_BLOCK_BORDER_COLOR": "#FF5C5C",
        "BLOCK_ENABLED_COLOR": "#252B34",
        "BLOCK_DISABLED_COLOR": "#1C2027",
        "BLOCK_BYPASSED_COLOR": "#22303F",
        "BLOCK_SHADOW_COLOR": "#55000000",
        "CONNECTION_ENABLED_COLOR": "#9AA6B8",
        "CONNECTION_DISABLED_COLOR": "#4A5361",
        "CONNECTION_ERROR_COLOR": "#FF5C5C",
        "FLOWGRAPH_BACKGROUND_COLOR": "#14181E",
        "GRID_MINOR_COLOR": "#1A1F26",
        "GRID_MAJOR_COLOR": "#222832",
        "VARIABLE_BACKGROUND_COLOR": "#1E242C",
        "VARIABLE_BORDER_COLOR": "#5C6676",
    },
}
# The classic "light" theme uses the modern canvas as well.
_PALETTES["light"] = _PALETTES["modern"]

CURRENT_THEME = "modern"


def set_theme(theme):
    """Rebind the module level canvas colors to the palette of `theme`."""
    global CURRENT_THEME
    palette = _PALETTES.get(theme, _PALETTES["modern"])
    CURRENT_THEME = theme if theme in _PALETTES else "modern"
    for name, value in palette.items():
        globals()[name] = get_color(value)


def is_dark():
    return CURRENT_THEME == "dark"


set_theme("modern")

# Kept for backwards compatibility with code that picks the background itself
DARK_FLOWGRAPH_BACKGROUND_COLOR = get_color(_PALETTES["dark"]["FLOWGRAPH_BACKGROUND_COLOR"])
LIGHT_FLOWGRAPH_BACKGROUND_COLOR = get_color(_PALETTES["modern"]["FLOWGRAPH_BACKGROUND_COLOR"])


#################################################################################
# port colors
#################################################################################
PORT_TYPE_TO_COLOR = {key: get_color(color) for name, key, sizeof, color in Constants.CORE_TYPES}
PORT_TYPE_TO_COLOR.update((key, get_color(color)) for key, (_, color) in Constants.ALIAS_TYPES.items())
