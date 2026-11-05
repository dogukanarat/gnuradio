# Test bench for the modern GRC Qt interface

Scripts used to develop and check the modern theme of the GRC Qt GUI
(`grc/gui_qt`) and the QT GUI plot theme (`gr-qtgui/themes/modern.qss`).
They run GRC straight from this source tree without an installed GNU Radio:
`stub/gnuradio` stands in for the few `gnuradio.gr` calls the GUI makes, and
all settings, caches and screenshots go to `out/` (or `$GRC_UI_OUT`).

Requirements: Python 3 with PyQt6, pyyaml, mako, jsonschema and markupsafe.
Without a display, Qt's `offscreen` platform is used automatically.
Blocks evaluate their parameters with the stub, so parameters that need real
GNU Radio modules (`analog.GR_COS_WAVE`, ...) are shown as errors; that is
expected here.

## Checks

    ./run_all_tests.sh

| Script | What it checks |
|---|---|
| `smoke.py` | ports, branches, moving/rotating blocks with undo, align, grid, status bar, ribbon state |
| `route_test.py` | orthogonal routes, no line through a block, feedback through the gap, re-routing after a move |
| `circle_props_test.py` | circle blocks: inputs at 90/180/270 deg entering straight, rotation, >3 inputs; properties dialog save/cancel |
| `overlap_test.py FG...` | no line runs on top of a line from another output |
| `dispatch_test.py` | Qt GUI is the default, `--gtk` / preference / missing PyQt6 select GTK |
| `prefs_runtime_test.py` | plot theme choice in Preferences > Runtime is saved to config.conf |
| `timing.py FG...` | time of a full re-route pass and of one drag step |

The router itself has unit tests in `grc/tests/test_qt_router.py`.

## Screenshots

    python3 run_grc.py out/main.png routing.grc            # main window
    GRC_THEME=dark python3 run_grc.py out/dark.png train_rot.grc
    GRC_RENDER=0,120,1340,800 python3 run_grc.py out/canvas.png train_rot.grc
    python3 props_shot.py props analog_sig_source_x_0 routing.grc
    python3 windows_shot.py light routing.grc               # every dialog, menu and dock -> out/windows/
    python3 sheet.py out/sheet.png 1600 out/windows/*.png   # contact sheet

`run_grc.py` documents its environment variables (theme, selection, zoom,
rendering a scene rectangle).

## Running QT GUI flowgraphs

`run_scopes.py` runs a generated QT GUI flowgraph and saves a screenshot of
its window, optionally with a style sheet. It needs a real GNU Radio
installation and a display (e.g. `xvfb-run`):

    grcc -o out scopes.grc
    xvfb-run -a python3 run_scopes.py out/scopes.py out/scopes.png 6 ../../gr-qtgui/themes/modern.qss

## Flowgraphs

`sine_noise.grc` (small chain with a branch), `routing.grc` (branches,
feedback, a long line past other blocks), `train.grc` / `train_rot.grc`
(a two-mass model laid out like a Simulink example, without and with turned
blocks), `scopes.grc` (time, frequency and waterfall sinks).
