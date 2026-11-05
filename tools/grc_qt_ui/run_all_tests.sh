#!/bin/sh
# Run every GUI check of the modern GRC Qt interface. Needs PyQt6, pyyaml,
# mako and jsonschema; GNU Radio itself is not needed (see stub/).
set -e
cd "$(dirname "$0")"
PY=${PYTHON:-python3}
status=0
for test in smoke.py route_test.py circle_props_test.py; do
    echo "== $test"
    $PY -I "$test" 2>/dev/null | grep -E "FAIL|passed" || status=1
done
echo "== overlap_test.py"
$PY -I overlap_test.py train.grc train_rot.grc routing.grc sine_noise.grc \
    ../../gr-analog/examples/noise_power.grc 2>/dev/null | grep -E "overlaps|  \(" || status=1
echo "== dispatch_test.py"
$PY -I dispatch_test.py 2>/dev/null | grep -E "PASS|FAIL" || status=1
for pick in 0 1 6; do
    echo "== prefs_runtime_test.py (choice $pick)"
    PICK=$pick $PY -I prefs_runtime_test.py "" out/prefs_runtime.png 2>/dev/null | grep "saved value" || status=1
done
exit $status
