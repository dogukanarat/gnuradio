"""Lay out screenshots on a sheet with captions. usage: sheet.py out.png width name1 name2 ..."""
import sys
import os
from PyQt6.QtWidgets import QApplication
app = QApplication(sys.argv[:1])
from PyQt6.QtGui import QImage, QPainter, QColor, QFont
from PyQt6.QtCore import Qt, QRect
out_name, width = sys.argv[1], int(sys.argv[2])
files = sys.argv[3:]
imgs = [(os.path.basename(f)[:-4], QImage(f)) for f in files]
pad, cap = 12, 22
# simple shelf packing
x = y = pad
row_h = 0
places = []
for name, im in imgs:
    if im.width() > width - 2 * pad:
        im = im.scaledToWidth(width - 2 * pad, Qt.TransformationMode.SmoothTransformation)
    if x + im.width() > width - pad:
        x = pad
        y += row_h + pad
        row_h = 0
    places.append((name, im, x, y))
    x += im.width() + pad
    row_h = max(row_h, im.height() + cap)
H = y + row_h + pad
out = QImage(width, H, QImage.Format.Format_RGB32)
out.fill(QColor("#9AA3AF"))
p = QPainter(out)
f = QFont()
f.setPointSize(9)
f.setBold(True)
p.setFont(f)
for name, im, x, y in places:
    p.setPen(QColor("#111"))
    p.drawText(QRect(x, y, im.width(), cap), Qt.AlignmentFlag.AlignVCenter, name)
    p.drawImage(x, y + cap, im)
p.end()
out.save(out_name)
print(out_name, width, H)
