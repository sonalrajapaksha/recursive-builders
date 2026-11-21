"""Navigation + terrain for the mech bot. Stdlib only, never prints.

Load: world.json prisms + terrain.i16 -> 1 m node mask (prisms, bounds, steep ground), dilated by the
mech radius with row bitmasks (hard) and radius+3 m (soft, used as a path-cost penalty), then a 2 m
coarse grid used by A*. Per-tick steer() mostly just follows a cached path.
"""
import heapq
import json
import math
import os
import sys
import time
from array import array
from collections import deque

_T01 = bytes([48, 49] + [48] * 254)          # 0/1 bytes -> '0'/'1'
_TBIN = bytes([0] * 48 + [0, 1] + [0] * 206)  # '0'/'1' -> 0/1
_NB = ((1, 0, 1.0), (-1, 0, 1.0), (0, 1, 1.0), (0, -1, 1.0),
       (1, 1, 1.414), (1, -1, 1.414), (-1, 1, 1.414), (-1, -1, 1.414))
_EC = 16.0  # exposure map cell (m)
_PEN = 6.0   # exposure cost: an open cell costs up to 1+_PEN times a sheltered one
_DETOUR = 1.35  # accept an exposure-aware route only if it is at most this much longer
_CS = 16.0  # spatial hash cell for prisms


def _mech_of(cfg):
    if not cfg:
        return {}
    return cfg.get("mech", cfg) if isinstance(cfg, dict) else {}


def _pip(edges, x, y):
    c = False
    for x0, y0, x1, y1 in edges:
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            c = not c
    return c


def _seg_cross(edges, ax, ay, bx, by):
    dx = bx - ax
    dy = by - ay
    for x0, y0, x1, y1 in edges:
        ex = x1 - x0
        ey = y1 - y0
        den = dx * ey - dy * ex
        if den == 0.0:
            continue
        t = ((x0 - ax) * ey - (y0 - ay) * ex) / den
        u = ((x0 - ax) * dy - (y0 - ay) * dx) / den
        if 0.0 <= t <= 1.0 and 0.0 <= u <= 1.0:
            return True
    return False


def _edge_d2(edges, x, y):
    best = 1e18
    for x0, y0, x1, y1 in edges:
        ex = x1 - x0
        ey = y1 - y0
        l2 = ex * ex + ey * ey
        t = 0.0 if l2 == 0.0 else max(0.0, min(1.0, ((x - x0) * ex + (y - y0) * ey) / l2))
        px = x0 + t * ex - x
        py = y0 + t * ey - y
        d = px * px + py * py
        if d < best:
            best = d
    return best


class Nav:
    def __init__(self, map_dir, cfg=None):
        d = map_dir
        if not os.path.exists(os.path.join(d, "world.json")):
            d = os.path.join(map_dir, "v2")
        with open(os.path.join(d, "world.json")) as f:
            w = json.load(f)
        t = w["terrain"]
        self.nx, self.ny = t["nx"], t["ny"]
        self.minx, self.miny, self.step = t["minX"], t["minY"], t["step"]
        ter = array("h")
        with open(os.path.join(d, t["file"]), "rb") as f:
            ter.frombytes(f.read())
        if sys.byteorder == "big":
            ter.byteswap()
        self.ter = ter
        self.bounds = w["bounds"]
        self.prisms = []  # (base, top, edges, xmin, ymin, xmax, ymax)
        self._hash = {}
        for p in w["prisms"]:
            edges = []
            xs = []
            ys = []
            for r in [p["ring"]] + list(p.get("holes") or []):
                n = len(r) // 2
                for k in range(n):
                    x0, y0 = r[2 * k], r[2 * k + 1]
                    x1, y1 = r[2 * ((k + 1) % n)], r[2 * ((k + 1) % n) + 1]
                    edges.append((x0, y0, x1, y1))
                if r is p["ring"]:
                    xs = r[0::2]
                    ys = r[1::2]
            idx = len(self.prisms)
            pr = (p["base"], p["top"], edges, min(xs), min(ys), max(xs), max(ys))
            self.prisms.append(pr)
            for ci in range(int(math.floor(pr[3] / _CS)), int(math.floor(pr[5] / _CS)) + 1):
                for cj in range(int(math.floor(pr[4] / _CS)), int(math.floor(pr[6] / _CS)) + 1):
                    self._hash.setdefault((ci, cj), []).append(idx)
        self._key = None
        self.dyn = {}
        self.tick = 0
        self._hist = deque()
        self._steered = False
        self._rec_until = -1
        self._nstuck = 0
        self._last_stuck = -9999
        self._rot = 0.0
        self._last_h = (1.0, 0.0)
        self._path = None
        self._pi = 0
        self._pgoal = None
        self.calm = False      # set by the policy: no enemy known near -> prefer low-exposure routes
        self._build(self._key_of(_mech_of(cfg)))
        self._build_exposure()

    # ---------------------------------------------------------------- build
    @staticmethod
    def _key_of(m):
        return (float(m.get("radius", 2.5)), float(m.get("height", 9.0)),
                float(m.get("step_up", 1.2)), float(m.get("max_slope_deg", 50.0)))

    def _ensure(self, cfg):
        m = _mech_of(cfg)
        if m:
            k = self._key_of(m)
            if k != self._key:
                self._build(k)

    def _build(self, key):
        self._key = key
        self.r, self.H, self.su, self.slope = key
        nx, ny, minx, miny, st, ter = self.nx, self.ny, self.minx, self.miny, self.step, self.ter
        H, su = self.H, self.su
        rows = [bytearray(nx) for _ in range(ny)]
        # prisms
        for base, top, edges, bx0, by0, bx1, by1 in self.prisms:
            j0 = max(0, int(math.ceil((by0 - miny) / st)))
            j1 = min(ny - 1, int(math.floor((by1 - miny) / st)))
            for j in range(j0, j1 + 1):
                y = miny + j * st
                xs = []
                for x0, y0, x1, y1 in edges:
                    if (y0 <= y) != (y1 <= y):
                        xs.append(x0 + (y - y0) * (x1 - x0) / (y1 - y0))
                xs.sort()
                row = rows[j]
                off = j * nx
                for k in range(0, len(xs) - 1, 2):
                    i0 = max(0, int(math.ceil((xs[k] - minx) / st)))
                    i1 = min(nx - 1, int(math.floor((xs[k + 1] - minx) / st)))
                    for i in range(i0, i1 + 1):
                        g = ter[off + i] * 0.01
                        if base < g + H and top > g + su:
                            row[i] = 1
        # steep ground
        thr = math.tan(math.radians(self.slope)) * st * 100.0
        steep = bytearray(nx * ny)
        prev = None
        for j in range(ny):
            r = ter[j * nx:(j + 1) * nx]
            row = rows[j]
            for i in [i for i, (p, q) in enumerate(zip(r, r[1:])) if abs(p - q) > thr]:
                row[i] = row[i + 1] = 1
                steep[j * nx + i] = steep[j * nx + i + 1] = 1
            if prev is not None:
                prow = rows[j - 1]
                for i in [i for i, (p, q) in enumerate(zip(prev, r)) if abs(p - q) > thr]:
                    row[i] = prow[i] = 1
                    steep[j * nx + i] = steep[(j - 1) * nx + i] = 1
            prev = r
        # bounds
        b = self.bounds
        for j in range(ny):
            y = miny + j * st
            row = rows[j]
            if y < b["minY"] or y > b["maxY"]:
                row[:] = b"\x01" * nx
            else:
                for i in range(nx):
                    x = minx + i * st
                    if x >= b["minX"]:
                        break
                    row[i] = 1
                for i in range(nx - 1, -1, -1):
                    x = minx + i * st
                    if x <= b["maxX"]:
                        break
                    row[i] = 1
        self.steep = steep
        ints = [int(bytes(r).translate(_T01).decode()[::-1], 2) for r in rows]
        self.hard = self._dilate(ints, self.r + 0.5)
        self.soft = self._dilate(ints, self.r + 3.5)
        # coarse 2 m grid
        self.cnx = (nx + 1) // 2
        self.cny = (ny + 1) // 2
        self.cn = self.cnx * self.cny
        ch = bytearray()
        cs = bytearray()
        for cj in range(self.cny):
            ch += self.hard[2 * cj * nx:(2 * cj + 1) * nx:2]
            cs += self.soft[2 * cj * nx:(2 * cj + 1) * nx:2]
        self.chard, self.csoft = ch, cs
        self._G = [0.0] * self.cn
        self._ST = [0] * self.cn
        self._CL = [0] * self.cn
        self._PA = [0] * self.cn
        self._cur = 0
        self._label()
        self.dyn = {}
        self._path = None

    def _dilate(self, ints, rad):
        nx, ny = self.nx, self.ny
        full = (1 << nx) - 1
        R = int(rad)
        hs = {}
        for dy in range(-R, R + 1):
            hw = int(math.sqrt(max(0.0, rad * rad - dy * dy)))
            if hw in hs:
                continue
            hs[hw] = [self._hdil(v, hw, full) for v in ints]
        out = [0] * ny
        for dy in range(-R, R + 1):
            hw = int(math.sqrt(max(0.0, rad * rad - dy * dy)))
            src = hs[hw]
            for j in range(ny):
                k = j + dy
                if 0 <= k < ny:
                    out[j] |= src[k]
        res = bytearray()
        for v in out:
            res += format(v, "0%db" % nx)[::-1].encode().translate(_TBIN)
        return res

    @staticmethod
    def _hdil(v, hw, full):
        o = v
        for d in range(1, hw + 1):
            o |= (v << d) | (v >> d)
        return o & full

    def _label(self):
        cnx, cny, chard, nx, hard = self.cnx, self.cny, self.chard, self.nx, self.hard
        comp = [0] * self.cn
        n = 0
        sizes = {}
        for s in range(self.cn):
            if chard[s] or comp[s]:
                continue
            n += 1
            comp[s] = n
            q = [s]
            cnt = 0
            while q:
                c = q.pop()
                cnt += 1
                i = c % cnx
                j = c // cnx
                for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ni = i + di
                    nj = j + dj
                    if ni < 0 or nj < 0 or ni >= cnx or nj >= cny:
                        continue
                    m = nj * cnx + ni
                    if chard[m] or comp[m] or hard[(2 * j + dj) * nx + 2 * i + di]:
                        continue
                    comp[m] = n
                    q.append(m)
            sizes[n] = cnt
        self.comp = comp
        self.main = max(sizes, key=sizes.get) if sizes else 0

    # ---------------------------------------------------------------- terrain
    def ground(self, x, y):
        nx, ny = self.nx, self.ny
        fx = (x - self.minx) / self.step
        fy = (y - self.miny) / self.step
        fx = 0.0 if fx < 0.0 else (nx - 1.0001 if fx > nx - 1.0001 else fx)
        fy = 0.0 if fy < 0.0 else (ny - 1.0001 if fy > ny - 1.0001 else fy)
        i = int(fx)
        j = int(fy)
        tx = fx - i
        ty = fy - j
        t = self.ter
        k = j * nx + i
        a = t[k]
        b = t[k + 1]
        c = t[k + nx]
        d = t[k + nx + 1]
        return 0.01 * ((a + (b - a) * tx) * (1.0 - ty) + (c + (d - c) * tx) * ty)

    def blocked(self, x, y, z=None):
        nx, ny = self.nx, self.ny
        i = int(x - self.minx + 0.5)
        j = int(y - self.miny + 0.5)
        if i < 0 or j < 0 or i >= nx or j >= ny:
            return True
        if z is None:
            return self.hard[j * nx + i] == 1
        b = self.bounds
        r = self.r
        if x < b["minX"] + r or x > b["maxX"] - r or y < b["minY"] + r or y > b["maxY"] - r:
            return True
        if self.steep[j * nx + i]:
            return True
        r2 = r * r
        seen = set()
        for ci in range(int(math.floor((x - r) / _CS)), int(math.floor((x + r) / _CS)) + 1):
            for cj in range(int(math.floor((y - r) / _CS)), int(math.floor((y + r) / _CS)) + 1):
                for idx in self._hash.get((ci, cj), ()):
                    if idx in seen:
                        continue
                    seen.add(idx)
                    base, top, edges, x0, y0, x1, y1 = self.prisms[idx]
                    if not (base < z + self.H and top > z + self.su):
                        continue
                    if x < x0 - r or x > x1 + r or y < y0 - r or y > y1 + r:
                        continue
                    if _pip(edges, x, y) or _edge_d2(edges, x, y) < r2:
                        return True
        return False

    # ---------------------------------------------------------------- LOS
    def los(self, a, b):
        ax, ay = a[0], a[1]
        bx, by = b[0], b[1]
        az = a[2] if len(a) > 2 else self.ground(ax, ay) + 8.0
        bz = b[2] if len(b) > 2 else self.ground(bx, by) + 4.5
        dx = bx - ax
        dy = by - ay
        dz = bz - az
        L = math.hypot(dx, dy)
        n = int(L / 2.0) + 1
        for k in range(1, n):
            t = k / n
            if self.ground(ax + dx * t, ay + dy * t) > az + dz * t + 0.3:
                return False
        cand = set()
        m = int(L / 8.0) + 1
        for k in range(m):
            t0 = k / m
            t1 = (k + 1) / m
            xa, xb = ax + dx * t0, ax + dx * t1
            ya, yb = ay + dy * t0, ay + dy * t1
            for ci in range(int(math.floor(min(xa, xb) / _CS)), int(math.floor(max(xa, xb) / _CS)) + 1):
                for cj in range(int(math.floor(min(ya, yb) / _CS)), int(math.floor(max(ya, yb) / _CS)) + 1):
                    cand.update(self._hash.get((ci, cj), ()))
        sx0, sx1 = min(ax, bx), max(ax, bx)
        sy0, sy1 = min(ay, by), max(ay, by)
        for idx in cand:
            base, top, edges, x0, y0, x1, y1 = self.prisms[idx]
            if sx1 < x0 or sx0 > x1 or sy1 < y0 or sy0 > y1:
                continue
            if dz == 0.0:
                if not (base < az < top):
                    continue
                lo, hi = 0.0, 1.0
            else:
                t_a = (base - az) / dz
                t_b = (top - az) / dz
                lo = max(0.0, min(t_a, t_b))
                hi = min(1.0, max(t_a, t_b))
                if lo > hi:
                    continue
            px, py = ax + dx * lo, ay + dy * lo
            qx, qy = ax + dx * hi, ay + dy * hi
            if _pip(edges, px, py) or _pip(edges, qx, qy) or _seg_cross(edges, px, py, qx, qy):
                return False
        return True

    # ---------------------------------------------------------------- grid helpers
    def _line_free(self, x0, y0, x1, y1):
        nx, ny, hard = self.nx, self.ny, self.hard
        d = math.hypot(x1 - x0, y1 - y0)
        n = int(d) + 1
        ux = (x1 - x0) / n
        uy = (y1 - y0) / n
        ox = x0 - self.minx + 0.5
        oy = y0 - self.miny + 0.5
        for k in range(3 if n > 4 else 1, n + 1):
            i = int(ox + ux * k)
            j = int(oy + uy * k)
            if i < 0 or j < 0 or i >= nx or j >= ny or hard[j * nx + i]:
                return False
        return True

    def _cell(self, x, y):
        ci = int((x - self.minx) / (2 * self.step) + 0.5)
        cj = int((y - self.miny) / (2 * self.step) + 0.5)
        ci = 0 if ci < 0 else (self.cnx - 1 if ci >= self.cnx else ci)
        cj = 0 if cj < 0 else (self.cny - 1 if cj >= self.cny else cj)
        return cj * self.cnx + ci

    def _xy(self, c):
        return (self.minx + 2 * self.step * (c % self.cnx), self.miny + 2 * self.step * (c // self.cnx))

    def _near_walk(self, c, maxr=8):
        if not self.chard[c]:
            return c
        cnx, cny = self.cnx, self.cny
        ci, cj = c % cnx, c // cnx
        for r in range(1, maxr + 1):
            best = None
            bd = 1e9
            for dj in range(-r, r + 1):
                for di in range(-r, r + 1):
                    if max(abs(di), abs(dj)) != r:
                        continue
                    ni, nj = ci + di, cj + dj
                    if 0 <= ni < cnx and 0 <= nj < cny:
                        m = nj * cnx + ni
                        if not self.chard[m] and di * di + dj * dj < bd:
                            bd = di * di + dj * dj
                            best = m
            if best is not None:
                return best
        return None

    # ---------------------------------------------------------------- exposure
    def _build_exposure(self, budget=1.6):
        """Coarse (_EC m) map of how open each spot is: fraction of 8 rays (eye 8 m, 150 m) with clear LOS.
        Time-boxed; cells are visited in a scattered order so a cut-off still leaves an even coverage."""
        t0 = time.perf_counter()
        b = self.bounds
        self.ex0, self.ey0 = b["minX"], b["minY"]
        self.ecx = int((b["maxX"] - b["minX"]) / _EC) + 1
        self.ecy = int((b["maxY"] - b["minY"]) / _EC) + 1
        n = self.ecx * self.ecy
        E = bytearray(b"\xff" * n)   # 255 = unknown
        dirs = [(math.cos(k * math.pi / 4 + 0.2), math.sin(k * math.pi / 4 + 0.2)) for k in range(8)]
        stride = 7919 if n % 7919 else 7907
        for q in range(n):
            if (q & 31) == 0 and time.perf_counter() - t0 > budget:
                break
            c = (q * stride) % n
            x = self.ex0 + (c % self.ecx + 0.5) * _EC
            y = self.ey0 + (c // self.ecx + 0.5) * _EC
            if self.blocked(x, y):
                continue
            eye = (x, y, self.ground(x, y) + 8.0)
            op = 0
            for ux, uy in dirs:
                fx, fy = x + ux * 150.0, y + uy * 150.0
                if not (b["minX"] <= fx <= b["maxX"] and b["minY"] <= fy <= b["maxY"]) or self.los(eye, (fx, fy)):
                    op += 1
            E[c] = op * 255 // 8 if op * 255 // 8 < 255 else 254
        self.expo = E
        self.expo_ms = (time.perf_counter() - t0) * 1000.0

    def exposure(self, x, y):
        """0 (sheltered) .. 1 (open on every side); 0.5 where unknown."""
        i = int((x - self.ex0) / _EC)
        j = int((y - self.ey0) / _EC)
        if i < 0 or j < 0 or i >= self.ecx or j >= self.ecy:
            return 0.5
        v = self.expo[j * self.ecx + i]
        return 0.5 if v == 255 else v / 254.0

    # ---------------------------------------------------------------- A*
    def _astar(self, s, g, budget=0.012, pen=0.0):
        cnx, cny, chard, csoft, hard, nx = self.cnx, self.cny, self.chard, self.csoft, self.hard, self.nx
        dyn = self.dyn
        expo, ecx = self.expo, self.ecx
        ex0, ey0 = self.ex0, self.ey0
        cs2 = 2 * self.step
        G, ST, CL, PA = self._G, self._ST, self._CL, self._PA
        self._cur += 1
        cur = self._cur
        gi, gj = g % cnx, g // cnx
        si, sj = s % cnx, s // cnx
        dx, dy = abs(si - gi), abs(sj - gj)
        hs = (dx + dy) - 0.586 * min(dx, dy)
        G[s] = 0.0
        ST[s] = cur
        PA[s] = -1
        hw = 1.5 + 0.3 * pen   # inflated costs need a greedier heuristic to stay fast
        heap = [(hs * hw, s)]
        best, bh = s, hs
        t0 = time.perf_counter()
        cnt = 0
        reached = False
        while heap:
            f, n = heapq.heappop(heap)
            if CL[n] == cur:
                continue
            CL[n] = cur
            if n == g:
                best = n
                reached = True
                break
            cnt += 1
            if cnt & 127 == 0 and time.perf_counter() - t0 > budget:
                break
            i = n % cnx
            j = n // cnx
            gn = G[n]
            for di, dj, c in _NB:
                ni = i + di
                nj = j + dj
                if ni < 0 or nj < 0 or ni >= cnx or nj >= cny:
                    continue
                m = nj * cnx + ni
                if chard[m] or CL[m] == cur or (dyn and m in dyn):
                    continue
                if di and dj:
                    if chard[j * cnx + ni] or chard[nj * cnx + i]:
                        continue
                elif hard[(2 * j + dj) * nx + 2 * i + di]:
                    continue
                if pen:
                    ev = expo[int((self.miny + nj * cs2 - ey0) / _EC) * ecx + int((self.minx + ni * cs2 - ex0) / _EC)]
                    ng = gn + c * (1 + csoft[m] + (0.5 if ev == 255 else ev / 254.0) * pen)
                else:
                    ng = gn + c * (1 + csoft[m])
                if ST[m] != cur or ng < G[m]:
                    ST[m] = cur
                    G[m] = ng
                    PA[m] = n
                    ex, ey = abs(ni - gi), abs(nj - gj)
                    h = (ex + ey) - 0.586 * min(ex, ey)
                    if h < bh:
                        bh = h
                        best = m
                    heapq.heappush(heap, (ng + h * hw, m))
        out = []
        n = best
        while n != -1:
            out.append(n)
            n = PA[n]
        out.reverse()
        return out, reached

    def path(self, pos, goal_xy):
        s = self._near_walk(self._cell(pos[0], pos[1]))
        g = self._near_walk(self._cell(goal_xy[0], goal_xy[1]))
        if s is None or g is None or self.comp[s] != self.comp[g]:
            return None
        cells, reached = self._astar(s, g)
        if self.calm and reached and len(cells) > 40:
            c2, r2 = self._astar(s, g, budget=0.006, pen=_PEN)
            if r2 and len(c2) <= _DETOUR * len(cells) + 2:
                cells = c2
        pts = [self._xy(c) for c in cells[1:]]
        pts.append((goal_xy[0], goal_xy[1]))
        return pts

    # ---------------------------------------------------------------- steering
    def _avoid(self, x, y, hx, hy):
        ang = math.atan2(hy, hx)
        for off in (0.0, 0.45, -0.45, 0.9, -0.9, 1.4, -1.4, 2.0, -2.0):
            a = ang + off
            c, s = math.cos(a), math.sin(a)
            if self._line_free(x, y, x + c * 6.0, y + s * 6.0):
                return c, s
        return hx, hy

    def steer(self, pos, goal_xy, cfg, vel=None, track=True):
        self._ensure(cfg)
        x, y = pos[0], pos[1]
        gx, gy = goal_xy[0], goal_xy[1]
        dx, dy = gx - x, gy - y
        d = math.hypot(dx, dy)
        if d < 1.0:
            return [0.0, 0.0], False, False
        self._steered = track  # strafing/flee headings are not goal travel: never count as stuck
        hx, hy = dx / d, dy / d
        if d <= (25.0 if self.calm else 80.0) and self._line_free(x, y, gx, gy):
            h = (hx, hy)
        else:
            h = self._follow(x, y, gx, gy, d, hx, hy)
        self._last_h = h
        if self.tick < self._rec_until:  # stuck recovery: rotate, jump + jet over the ledge
            a = math.atan2(h[1], h[0]) + self._rot
            return [math.cos(a), math.sin(a)], True, True
        return [h[0], h[1]], False, False

    def _follow(self, x, y, gx, gy, d, hx, hy):
        P = self._path
        if P is not None and self._pgoal is not None and math.hypot(gx - self._pgoal[0], gy - self._pgoal[1]) > 8.0:
            P = None
        if P is not None:
            lo = self._pi
            hi = min(len(P), lo + 20)
            k = min(range(lo, hi), key=lambda k: (P[k][0] - x) ** 2 + (P[k][1] - y) ** 2)
            self._pi = k
            if math.hypot(P[k][0] - x, P[k][1] - y) > 10.0 or (k >= len(P) - 1 and d > 4.0):
                P = None
        if P is None:
            P = self.path((x, y), (gx, gy))
            self._path = P
            self._pi = 0
            self._pgoal = (gx, gy)
            if P is None:
                return self._avoid(x, y, hx, hy)
        pi = self._pi
        best = min(pi + 1, len(P) - 1)
        for k in range(min(len(P), pi + (5 if self.calm else 15)) - 1, pi, -1):
            if self._line_free(x, y, P[k][0], P[k][1]):
                best = k
                break
        tx, ty = P[best]
        td = math.hypot(tx - x, ty - y)
        if td < 0.5:
            return hx, hy
        return (tx - x) / td, (ty - y) / td

    def note_progress(self, pos, tick):
        self.tick = tick
        h = self._hist
        h.append((tick, pos[0], pos[1], self._steered))
        self._steered = False
        while h and h[0][0] < tick - 40:
            h.popleft()
        if self.dyn and tick % 20 == 0:
            for k in [k for k, e in self.dyn.items() if e < tick]:
                del self.dyn[k]
        if tick < self._rec_until:
            return True
        if h and h[0][0] <= tick - 30 and math.hypot(pos[0] - h[0][1], pos[1] - h[0][2]) < 3.0 \
                and sum(1 for e in h if e[3]) >= 0.7 * len(h):
            self._nstuck = self._nstuck + 1 if tick - self._last_stuck < 200 else 1
            self._last_stuck = tick
            n = self._nstuck
            self._rot = (0.0, 1.2, -1.2, 2.4, -2.4)[(n - 1) % 5]
            self._rec_until = tick + 10
            if n >= 2:
                c = self._cell(pos[0], pos[1])
                ci, cj = c % self.cnx, c // self.cnx
                for di in (-1, 0, 1):
                    for dj in (-1, 0, 1):
                        if (di or dj) and 0 <= ci + di < self.cnx and 0 <= cj + dj < self.cny:
                            self.dyn[(cj + dj) * self.cnx + ci + di] = tick + 300
            self._path = None
            h.clear()
            return True
        return False

    # ---------------------------------------------------------------- zone
    def safe_point(self, center, radius, from_pos):
        cx, cy = center[0], center[1]
        fx, fy = from_pos[0], from_pos[1]
        s = self._near_walk(self._cell(fx, fy))
        rr = max(radius - 6.0, radius * 0.5)
        cands = [(cx, cy)]
        for fr in (0.3, 0.6, 1.0):
            for k in range(16):
                a = k * math.pi / 8
                cands.append((cx + math.cos(a) * rr * fr, cy + math.sin(a) * rr * fr))
        best = None
        bs = 1e18
        for pass_soft in (True, False):
            for px, py in cands:
                c = self._cell(px, py)
                if self.chard[c] or (pass_soft and self.csoft[c]):
                    continue
                if s is not None and self.comp[c] != self.comp[s]:
                    continue
                cxp, cyp = self._xy(c)
                sc = math.hypot(cxp - fx, cyp - fy) + 0.25 * math.hypot(cxp - cx, cyp - cy)
                if sc < bs:
                    bs, best = sc, (cxp, cyp)
            if best:
                break
        return best if best else (cx, cy)
