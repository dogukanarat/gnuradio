"""Find collinear overlaps between connections that come from different outputs."""
LANE = 6.0


def segments(gui):
    line = gui._line
    pts = [(line.elementAt(i).x, line.elementAt(i).y) for i in range(line.elementCount())]
    return list(zip(pts, pts[1:]))


def overlaps(fg, min_len=3.0):
    found = []
    conns = list(fg.connections)
    for i, a in enumerate(conns):
        for b in conns[i + 1:]:
            if a.source_port is b.source_port:
                continue  # branches of one output may share their trunk
            for (p1, p2) in segments(a.gui):
                for (q1, q2) in segments(b.gui):
                    if abs(p1[1] - p2[1]) < .01 and abs(q1[1] - q2[1]) < .01 and abs(p1[1] - q1[1]) < LANE:
                        lo = max(min(p1[0], p2[0]), min(q1[0], q2[0]))
                        hi = min(max(p1[0], p2[0]), max(q1[0], q2[0]))
                    elif abs(p1[0] - p2[0]) < .01 and abs(q1[0] - q2[0]) < .01 and abs(p1[0] - q1[0]) < LANE:
                        lo = max(min(p1[1], p2[1]), min(q1[1], q2[1]))
                        hi = min(max(p1[1], p2[1]), max(q1[1], q2[1]))
                    else:
                        continue
                    if hi - lo > min_len:
                        found.append((a.source_block.name, a.sink_block.name, b.source_block.name, b.sink_block.name,
                                      round(hi - lo)))
    return found
