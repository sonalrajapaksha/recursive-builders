import math
import os
import random
import sys
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import nav as navmod  # noqa: E402

ARENA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "arena")
CFG = {"mech": {"radius": 2.5, "height": 9, "step_up": 1.2, "max_slope_deg": 50}}
T0 = time.perf_counter()
NAV = navmod.Nav(ARENA)
LOAD = time.perf_counter() - T0


def centroid(p):
    pts = [(e[0], e[1]) for e in p[2]]
    return sum(a for a, _ in pts) / len(pts), sum(b for _, b in pts) / len(pts)


def big_building():
    """A building whose centroid is inside it and which is big enough to detour around."""
    best = None
    for p in NAV.prisms:
        if p[1] - p[0] < 10 or p[1] - NAV.ground(*centroid(p)) < 10:
            continue
        w, h = p[5] - p[3], p[6] - p[4]
        cx, cy = centroid(p)
        if 25 < w < 70 and 25 < h < 70 and navmod._pip(p[2], cx, cy):
            best = p if best is None or w * h > (best[5] - best[3]) * (best[6] - best[4]) else best
    return best


class TestNav(unittest.TestCase):
    def test_load_time(self):
        self.assertLess(LOAD, 2.0, LOAD)

    def test_ground(self):
        t = NAV.ter
        nx = NAV.nx
        # exactly on a vertex
        i, j = 100, 200
        self.assertAlmostEqual(NAV.ground(NAV.minx + i, NAV.miny + j), t[j * nx + i] * 0.01, 6)
        # midpoint is the mean of four corners
        m = (t[j * nx + i] + t[j * nx + i + 1] + t[(j + 1) * nx + i] + t[(j + 1) * nx + i + 1]) * 0.0025
        self.assertAlmostEqual(NAV.ground(NAV.minx + i + .5, NAV.miny + j + .5), m, 6)
        # clamped outside the map, never raises
        NAV.ground(-1e5, 1e5)
        # spawn sample from the protocol example: z ~ -4.7 near (-218, -22)
        self.assertLess(abs(NAV.ground(-217.98, -22.04) - (-4.73)), 1.5)

    def test_blocked_inside_buildings(self):
        n = 0
        for p in NAV.prisms:
            cx, cy = centroid(p)
            if navmod._pip(p[2], cx, cy) and p[1] - NAV.ground(cx, cy) > 3 and p[0] < NAV.ground(cx, cy) + 5:
                self.assertTrue(NAV.blocked(cx, cy), (cx, cy))
                self.assertTrue(NAV.blocked(cx, cy, NAV.ground(cx, cy)))
                n += 1
        self.assertGreater(n, 50)
        self.assertTrue(NAV.blocked(1e5, 0))
        self.assertTrue(NAV.blocked(NAV.bounds["minX"] - 1, 0))

    def test_open_ground_free(self):
        rnd = random.Random(1)
        free = 0
        for _ in range(2000):
            x = rnd.uniform(-400, 450)
            y = rnd.uniform(-250, 300)
            free += not NAV.blocked(x, y)
        self.assertGreater(free, 800)

    def test_los_through_building(self):
        p = big_building()
        self.assertIsNotNone(p)
        cx, cy = centroid(p)
        g = NAV.ground(cx, cy)
        east = (p[5] + 15, cy, g + 8)
        west = (p[3] - 15, cy, g + 8)
        self.assertFalse(NAV.los(west, east))
        # same line far above the roof is clear
        self.assertTrue(NAV.los((west[0], cy, p[1] + 30), (east[0], cy, p[1] + 30)))
        self.assertTrue(NAV.los((west[0], cy, p[1] + 30), (west[0] - 5, cy, p[1] + 30)))

    def test_path_around_building(self):
        p = big_building()
        cx, cy = centroid(p)
        a = (p[3] - 20, cy)
        b = (p[5] + 20, cy)
        a = NAV._xy(NAV._near_walk(NAV._cell(*a)))
        b = NAV._xy(NAV._near_walk(NAV._cell(*b)))
        pts = NAV.path(a, b)
        self.assertIsNotNone(pts)
        self.assertLess(math.dist(pts[-1], b), 3.0)
        for q in pts:
            self.assertFalse(NAV.blocked(q[0], q[1], NAV.ground(*q)), q)
        L = sum(math.dist(pts[k], pts[k + 1]) for k in range(len(pts) - 1))
        self.assertGreater(L, math.dist(a, b) + 5)  # detour exists
        self.assertLess(L, 4 * math.dist(a, b) + 100)

    def test_steer_walks_around_building(self):
        p = big_building()
        cx, cy = centroid(p)
        a = NAV._xy(NAV._near_walk(NAV._cell(p[3] - 20, cy)))
        b = NAV._xy(NAV._near_walk(NAV._cell(p[5] + 20, cy)))
        pos = list(a)
        tick = 0
        for _ in range(900):
            mv, jump, boost = NAV.steer(pos, b, CFG)
            self.assertAlmostEqual(math.hypot(*mv), 1.0, 3) if math.dist(pos, b) > 1 else None
            pos[0] += mv[0] * 1.1
            pos[1] += mv[1] * 1.1
            tick += 2
            NAV.note_progress(pos, tick)
            if math.dist(pos, b) < 2:
                break
        self.assertLess(math.dist(pos, b), 3.0)

    def test_untracked_steer_never_stuck(self):
        n = navmod.Nav(ARENA)
        for k in range(1, 80):
            n.steer((0.0, 0.0), (0.0, 40.0), CFG, None, False)
            self.assertFalse(n.note_progress((0.0, 0.0), k * 2))

    def test_stuck_recovery(self):
        n = navmod.Nav(ARENA)
        pos = (0.0, 0.0)
        got = False
        for k in range(60):
            n.steer(pos, (100.0, 0.0), CFG)
            if n.note_progress(pos, k * 2):
                got = True
                break
        self.assertTrue(got)
        mv, jump, boost = n.steer(pos, (100.0, 0.0), CFG)
        self.assertTrue(jump and boost)
        # moving normally is not "stuck"
        n2 = navmod.Nav(ARENA)
        for k in range(80):
            n2.steer((k * 5.0, 0), (1000, 0), CFG)
            self.assertFalse(n2.note_progress((k * 5.0, 0), k * 2))
        # standing still without steering is not stuck
        n3 = navmod.Nav(ARENA)
        for k in range(80):
            self.assertFalse(n3.note_progress((0, 0), k * 2))

    def test_safe_point(self):
        c = (41.3, -72.8)
        for r in (20, 70, 140, 380):
            x, y = NAV.safe_point(c, r, (-200, -20))
            self.assertLessEqual(math.dist((x, y), c), r + 1)
            self.assertFalse(NAV.blocked(x, y))

    def test_steer_latency(self):
        rnd = random.Random(7)
        cells = [c for c in range(NAV.cn) if not NAV.chard[c] and NAV.comp[c] == NAV.main]
        lat = []
        for ep in range(60):
            a = NAV._xy(rnd.choice(cells))
            g = NAV._xy(rnd.choice(cells))
            pos = list(a)
            tick = 0
            for _ in range(120):
                t = time.perf_counter()
                mv, j, b = NAV.steer(pos, g, CFG)
                lat.append(time.perf_counter() - t)
                pos[0] += mv[0] * 1.1
                pos[1] += mv[1] * 1.1
                tick += 2
                t = time.perf_counter()
                NAV.note_progress(pos, tick)
                lat[-1] += time.perf_counter() - t
        lat.sort()
        pct = lambda q: lat[int(q * (len(lat) - 1))] * 1000
        print("\nload %.3fs steer ms: p50 %.2f p95 %.2f p99 %.2f max %.2f n=%d" %
              (LOAD, pct(.5), pct(.95), pct(.99), lat[-1] * 1000, len(lat)), file=sys.stderr)
        self.assertLess(pct(.99), 15.0)
        self.assertLess(lat[-1] * 1000, 40.0)

    def test_los_latency(self):
        rnd = random.Random(3)
        lat = []
        for _ in range(500):
            a = (rnd.uniform(-300, 400), rnd.uniform(-200, 300), 0)
            a = (a[0], a[1], NAV.ground(a[0], a[1]) + 8)
            b = (a[0] + rnd.uniform(-200, 200), a[1] + rnd.uniform(-200, 200), 0)
            b = (b[0], b[1], NAV.ground(b[0], b[1]) + 4.5)
            t = time.perf_counter()
            NAV.los(a, b)
            lat.append(time.perf_counter() - t)
        lat.sort()
        print("los ms p50 %.2f p99 %.2f max %.2f" % (lat[250] * 1000, lat[494] * 1000, lat[-1] * 1000), file=sys.stderr)
        self.assertLess(lat[494] * 1000, 10.0)


if __name__ == "__main__":
    unittest.main()
