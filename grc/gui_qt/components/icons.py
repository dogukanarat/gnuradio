"""
Copyright 2026 The GNU Radio Contributors
This file is part of GNU Radio

SPDX-License-Identifier: GPL-2.0-or-later

A small built-in line icon set for the modern GRC look.

The icons are 24x24 stroke drawings. They are rendered with QtSvg in the
color of the current theme, so the toolbar looks the same on every desktop
regardless of the installed icon theme. When QtSvg is not available,
`icon()` returns an empty QIcon and callers keep their theme icon.
"""

import logging

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap

try:
    from PyQt6.QtSvg import QSvgRenderer
    HAVE_SVG = True
except ImportError:  # pragma: no cover - depends on the PyQt6 packaging
    HAVE_SVG = False

log = logging.getLogger(f"grc.application.{__name__}")

# Path data only; the svg wrapper (stroke, size) is added in _svg().
# "F:" marks an element that is filled instead of stroked.
_ICONS = {
    "new": ['<path d="M6 3h8l4 4v14H6z"/>', '<path d="M14 3v4h4"/>', '<path d="M12 11v6M9 14h6"/>'],
    "open": ['<path d="M3 7V5h6l2 2h9v3"/>', '<path d="M3 7v12h15l3-9H6l-3 9"/>'],
    "save": ['<path d="M5 4h11l3 3v13H5z"/>', '<path d="M8 4v5h7V4"/>', '<path d="M8 20v-6h8v6"/>'],
    "save_as": ['<path d="M5 4h11l3 3v6"/>', '<path d="M5 4v16h7"/>', '<path d="M8 4v5h7V4"/>',
                '<path d="M14 21l1-3 5-5 2 2-5 5z"/>'],
    "close": ['<path d="M6 6l12 12M18 6L6 18"/>'],
    "undo": ['<path d="M9 7L4 12l5 5"/>', '<path d="M4 12h10a6 6 0 010 12"/>'],
    "redo": ['<path d="M15 7l5 5-5 5"/>', '<path d="M20 12H10a6 6 0 000 12"/>'],
    "cut": ['<circle cx="6" cy="18" r="3"/>', '<circle cx="18" cy="18" r="3"/>',
            '<path d="M8.5 16L18 4M15.5 16L6 4"/>'],
    "copy": ['<rect x="8" y="8" width="12" height="12" rx="1.5"/>', '<path d="M16 8V5a1 1 0 00-1-1H5a1 1 0 00-1 1v10a1 1 0 001 1h3"/>'],
    "paste": ['<path d="M9 4h6v3H9z"/>', '<path d="M15 5h3v15H6V5h3"/>', '<path d="M9 12h6M9 16h4"/>'],
    "delete": ['<path d="M4 7h16"/>', '<path d="M9 7V4h6v3"/>', '<path d="M6 7l1 13h10l1-13"/>',
               '<path d="M10 11v6M14 11v6"/>'],
    "select_all": ['<rect x="4" y="4" width="16" height="16" rx="1" stroke-dasharray="3 2"/>',
                   '<rect x="8" y="8" width="8" height="8"/>'],
    "rotate_ccw": ['<path d="M4 12a8 8 0 103-6.2"/>', '<path d="M4 4v5h5"/>'],
    "rotate_cw": ['<path d="M20 12a8 8 0 11-3-6.2"/>', '<path d="M20 4v5h-5"/>'],
    "enable": ['<rect x="4" y="6" width="16" height="12" rx="2"/>', '<path d="M8 12l3 3 5-6"/>'],
    "disable": ['<rect x="4" y="6" width="16" height="12" rx="2" stroke-dasharray="3 2"/>',
                '<path d="M9 10l6 4M15 10l-6 4"/>'],
    "bypass": ['<rect x="8" y="8" width="8" height="8" rx="1"/>', '<path d="M2 12h3M19 12h3"/>',
               '<path d="M5 12V4h14v8"/>'],
    "properties": ['<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/>',
                   '<circle cx="16" cy="6" r="2"/>', '<circle cx="10" cy="12" r="2"/>',
                   '<circle cx="18" cy="18" r="2"/>'],
    "find": ['<circle cx="11" cy="11" r="6"/>', '<path d="M20 20l-4.5-4.5"/>'],
    "errors": ['<path d="M12 3l9 16H3z"/>', '<path d="M12 10v4"/>', 'F:<circle cx="12" cy="17" r="1"/>'],
    "generate": ['<path d="M8 8l-4 4 4 4M16 8l4 4-4 4M13.5 5l-3 14"/>'],
    "execute": ['F:<path d="M7 4.5l13 7.5-13 7.5z"/>'],
    "kill": ['F:<rect x="6" y="6" width="12" height="12" rx="1.5"/>'],
    "reload": ['<path d="M20 11a8 8 0 00-14.5-4.5L4 8"/>', '<path d="M4 3v5h5"/>',
               '<path d="M4 13a8 8 0 0014.5 4.5L20 16"/>', '<path d="M20 21v-5h-5"/>'],
    "zoom_in": ['<circle cx="11" cy="11" r="6"/>', '<path d="M20 20l-4.5-4.5M8.5 11h5M11 8.5v5"/>'],
    "zoom_out": ['<circle cx="11" cy="11" r="6"/>', '<path d="M20 20l-4.5-4.5M8.5 11h5"/>'],
    "zoom_original": ['<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>', '<rect x="9" y="9" width="6" height="6"/>'],
    "toggle_grid": ['<path d="M4 4h16v16H4zM4 9.3h16M4 14.6h16M9.3 4v16M14.6 4v16"/>'],
    "vertical_align_top": ['<path d="M4 4h16"/>', '<rect x="6" y="7" width="4" height="11"/>',
                           '<rect x="14" y="7" width="4" height="6"/>'],
    "vertical_align_middle": ['<path d="M4 12h16"/>', '<rect x="6" y="6" width="4" height="12"/>',
                              '<rect x="14" y="9" width="4" height="6"/>'],
    "vertical_align_bottom": ['<path d="M4 20h16"/>', '<rect x="6" y="6" width="4" height="11"/>',
                              '<rect x="14" y="11" width="4" height="6"/>'],
    "horizontal_align_left": ['<path d="M4 4v16"/>', '<rect x="7" y="6" width="11" height="4"/>',
                              '<rect x="7" y="14" width="6" height="4"/>'],
    "horizontal_align_center": ['<path d="M12 4v16"/>', '<rect x="6" y="6" width="12" height="4"/>',
                                '<rect x="9" y="14" width="6" height="4"/>'],
    "horizontal_align_right": ['<path d="M20 4v16"/>', '<rect x="6" y="6" width="11" height="4"/>',
                               '<rect x="11" y="14" width="6" height="4"/>'],
    "create_hier": ['<rect x="3" y="3" width="7" height="6" rx="1"/>', '<rect x="14" y="15" width="7" height="6" rx="1"/>',
                    '<path d="M6.5 9v9H14"/>', '<path d="M10 6h7v9"/>'],
    "open_hier": ['<rect x="4" y="4" width="16" height="16" rx="1.5"/>', '<path d="M10 14l5-5M10 9h5v5"/>'],
    "toggle_source_bus": ['<path d="M4 7h10M4 12h10M4 17h10"/>', '<path d="M14 5v14"/>', '<path d="M14 12h6"/>'],
    "toggle_sink_bus": ['<path d="M20 7H10M20 12H10M20 17H10"/>', '<path d="M10 5v14"/>', '<path d="M10 12H4"/>'],
    "autoconnect": ['<rect x="2" y="9" width="6" height="6" rx="1"/>', '<rect x="16" y="9" width="6" height="6" rx="1"/>',
                    '<path d="M8 12h8"/>', '<path d="M13 9l3 3-3 3"/>'],
    "example_browser": ['<path d="M4 5a2 2 0 012-2h14v15H6a2 2 0 00-2 2z"/>', '<path d="M4 20a2 2 0 002 2h14v-4"/>',
                        '<path d="M9 8h7M9 12h5"/>'],
    "module_browser": ['<path d="M12 3l8 4.5v9L12 21l-8-4.5v-9z"/>', '<path d="M4 7.5l8 4.5 8-4.5M12 12v9"/>'],
    "filter_design_tool": ['<path d="M3 6h5c3 0 3 12 6 12h7"/>', '<path d="M3 20h18"/>'],
    "preferences": ['<circle cx="12" cy="12" r="3"/>',
                    '<path d="M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1L7 17M17 7l2.1-2.1"/>'],
    "screen_capture": ['<path d="M4 8h3l2-3h6l2 3h3v11H4z"/>', '<circle cx="12" cy="13" r="3.5"/>'],
    "help": ['<circle cx="12" cy="12" r="9"/>', '<path d="M9.5 9.5a2.5 2.5 0 015 0c0 2-2.5 2-2.5 4"/>',
             'F:<circle cx="12" cy="17" r="1"/>'],
    "types": ['<rect x="4" y="4" width="7" height="7" rx="1"/>', '<rect x="13" y="4" width="7" height="7" rx="1"/>',
              '<rect x="4" y="13" width="7" height="7" rx="1"/>', '<rect x="13" y="13" width="7" height="7" rx="1"/>'],
    "keys": ['<rect x="2" y="6" width="20" height="12" rx="2"/>', '<path d="M6 10h1M10 10h1M14 10h1M18 10h0M7 14h10"/>'],
    "view_undo_stack": ['<path d="M8 6h12M8 12h12M8 18h12"/>', '<path d="M4 6h0M4 12h0M4 18h0"/>'],
    "block_inc_type": ['<path d="M12 4v16M6 10l6-6 6 6"/>'],
    "block_dec_type": ['<path d="M12 4v16M6 14l6 6 6-6"/>'],
    "library": ['<rect x="3" y="4" width="18" height="16" rx="1.5"/>', '<path d="M9 4v16"/>',
                '<path d="M12 8h6M12 12h6M12 16h4"/>'],
    "start_profiler": ['<circle cx="12" cy="13" r="8"/>', '<path d="M12 13l4-4M10 2h4"/>'],
    "stop_profiler": ['<circle cx="12" cy="13" r="8"/>', 'F:<rect x="9" y="10" width="6" height="6"/>'],
    "close_all": ['<path d="M8 8l10 10M18 8L8 18"/>', '<path d="M4 15V4h11"/>'],
    "exit": ['<path d="M14 4h5v16h-5"/>', '<path d="M10 8l-4 4 4 4M6 12h10"/>'],
}


def _svg(name, color):
    parts = []
    for element in _ICONS[name]:
        if element.startswith("F:"):
            parts.append('<g fill="{0}" stroke="none">{1}</g>'.format(color, element[2:]))
        else:
            parts.append(element)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24" '
        'fill="none" stroke="{0}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">'
        '{1}</svg>'.format(color, "".join(parts))
    )


_cache = {}


def has(name):
    return HAVE_SVG and name in _ICONS


def icon(name, color="#2B3646", disabled_color="#A6AFBB"):
    """Return a QIcon for `name` drawn in `color`, or an empty QIcon."""
    if not has(name):
        return QIcon()
    key = (name, color, disabled_color)
    if key in _cache:
        return _cache[key]

    result = QIcon()
    for mode, col in ((QIcon.Mode.Normal, color), (QIcon.Mode.Disabled, disabled_color)):
        renderer = QSvgRenderer(QByteArray(_svg(name, col).encode()))
        for size in (16, 24, 32, 48):
            pixmap = QPixmap(size, size)
            pixmap.fill(Qt.GlobalColor.transparent)
            painter = QPainter(pixmap)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            renderer.render(painter, QRectF(0, 0, size, size))
            painter.end()
            result.addPixmap(pixmap, mode)
    _cache[key] = result
    return result
