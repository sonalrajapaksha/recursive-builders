"""recursive-builders policy: survival-first decision logic for mechfight/1.

Policy(hello, nav).act(obs) -> action dict. Stdlib only, never prints to stdout, never raises.
Modes (priority): zone retreat > flee > fight > loot/cubes/drop > farm > hide (stand still, regen).
All numbers come from hello["config"] / obs["self"]["stats"]; constants below are tuning only.
"""
import math
import sys

TAU = math.tau


def _g(d, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] is not None:
            d = d[k]
        else:
            return default
    return d


def _num(v, default=0.0):
    try:
        v = float(v)
        return v if math.isfinite(v) else default
    except (TypeError, ValueError):
        return default


def _vec(v, n=3):
    try:
        out = [_num(v[i]) for i in range(n)]
        return out
    except (TypeError, IndexError, KeyError):
        return None


def wrap(a):
    return (a + math.pi) % TAU - math.pi


def hyp(ax, ay):
    return math.hypot(ax, ay)


def unit(x, y):
    d = math.hypot(x, y)
    return (x / d, y / d) if d > 1e-9 else (0.0, 0.0)


def lead_point(src, tpos, tvel, speed, iters=3):
    """Intercept point for a straight projectile of constant speed."""
    t = math.dist(src, tpos) / max(speed, 1e-6)
    p = list(tpos)
    for _ in range(iters):
        p = [tpos[i] + tvel[i] * t for i in range(3)]
        t = math.dist(src, p) / max(speed, 1e-6)
    return p, t


def mortar_pitch(dh, dz, v, g):
    """Low-arc launch pitch to hit horizontal distance dh, height offset dz; None if out of range."""
    if dh < 1e-3:
        return None
    disc = v ** 4 - g * (g * dh * dh + 2 * dz * v * v)
    if disc < 0:
        return None
    return math.atan2(v * v - math.sqrt(disc), g * dh)


def zone_now(z, t):
    c = _vec(z.get("center"), 2) or [0.0, 0.0]
    r = _num(z.get("radius"), 1e9)
    nc = _vec(z.get("next_center"), 2) or c
    nr = _num(z.get("next_radius"), r)
    s = _num(z.get("shrink_start"), 1e9)
    e = _num(z.get("shrink_end"), s)
    if t <= s:
        return c[0], c[1], r
    if t >= e:
        return nc[0], nc[1], nr
    f = (t - s) / max(e - s, 1e-6)
    return c[0] + (nc[0] - c[0]) * f, c[1] + (nc[1] - c[1]) * f, r + (nr - r) * f


UPGRADE_WEIGHT = {
    "armor": 9, "plating": 8, "nanites": 7.5, "servos": 6.5, "sensors": 6.5, "laser_damage": 7,
    "laser_charge": 6, "gyros": 5.5, "gun_rate": 5.5, "gun_damage": 5, "jets": 5, "lightning_efficiency": 6,
    "lightning_range": 6, "mortar_reload": 5, "gun_mag": 4, "gun_velocity": 4, "reactor": 4, "capacitor": 4,
    "mortar_splash": 3.5, "mortar_velocity": 4, "lightning_chain": 4, "laser_pierce": 3,
}


class Policy:
    def __init__(self, hello, nav=None):
        self.nav = nav
        cfg = _g(hello, "config", default={}) or {}
        self.cfg = cfg
        self.mech = _g(cfg, "mech", default={}) or {}
        self.W = _g(cfg, "weapons", default={}) or {}
        self.upgrades_cfg = {u.get("id"): u for u in (cfg.get("upgrades") or []) if isinstance(u, dict)}
        self.pick_r = _num(_g(cfg, "loot", "pickup_radius"), 4.0)
        self.cube_r = _num(_g(cfg, "cubes", "pickup_radius"), 3.5)
        self.mem_s = _num(_g(cfg, "vision", "memory_s"), 5.0)
        self.near_r = _num(_g(cfg, "vision", "near_range"), 45.0)
        self.slot = _g(hello, "slot", default=-1)
        self.mem = {}          # enemy id -> dict(pos, vel, hp, weapons, t)
        self.bad = {}          # pickup id -> expiry t
        self.prov_until = -1.0
        self.threat_bearing = None
        self.threat_t = -99.0
        self.strafe = 1.0
        self.strafe_until = 0.0
        self.boost_on = False
        self.anchor = None
        self.anchor_t = -99.0
        self.anchor_key = None
        self.target_id = None
        self.danger = [0.0, 0.0]
        self.prev_pos = None
        self.stuck_n = 0
        self.last = {"move": [0.0, 0.0], "aim": [0.0, 0.0], "boost": False}
        self.errs = 0
        self.mode = "init"
        self.nav_ok = nav is not None

    # ------------------------------------------------------------------ public
    def act(self, obs):
        tick = obs.get("tick", 0) if isinstance(obs, dict) else 0
        try:
            a = self._decide(obs)
            a = self._sanitize(a, tick)
            self.last = {"move": a.get("move", [0.0, 0.0]), "aim": a.get("aim", self.last["aim"]),
                         "boost": a.get("boost", False)}
            return a
        except Exception as e:  # never raise
            self.errs += 1
            if self.errs <= 5:
                print("policy error:", repr(e), file=sys.stderr, flush=True)
            try:
                return self._sanitize(self._fallback(obs), tick)
            except Exception:
                return {"tick": tick, "move": [0.0, 0.0]}

    # ------------------------------------------------------------------ helpers
    def _sanitize(self, a, tick):
        out = {"tick": tick}
        mv = _vec(a.get("move"), 2) or [0.0, 0.0]
        l = hyp(*mv)
        if l > 1:
            mv = [mv[0] / l, mv[1] / l]
        out["move"] = mv
        out["boost"] = bool(a.get("boost", False))
        out["jump"] = bool(a.get("jump", False))
        aim = _vec(a.get("aim"), 2)
        if aim:
            lo, hi = _num(self.mech.get("min_pitch"), -0.7), _num(self.mech.get("max_pitch"), 1.3)
            out["aim"] = [wrap(aim[0]), min(max(aim[1], lo), hi)]
        f = a.get("fire")
        out["fire"] = [bool(f[0]), bool(f[1])] if isinstance(f, (list, tuple)) and len(f) >= 2 else [False, False]
        if a.get("reload"):
            out["reload"] = True
        for k in ("pick", "take", "drop"):
            if a.get(k) is not None:
                out[k] = int(a[k])
        if a.get("debug"):
            out["debug"] = a["debug"]
        return out

    def _fallback(self, obs):
        me = obs["self"]
        z = obs["zone"]
        nc = _vec(z.get("next_center"), 2) or [0.0, 0.0]
        p = me["pos"]
        d = unit(nc[0] - p[0], nc[1] - p[1])
        a = {"tick": obs.get("tick", 0), "move": list(d), "aim": [math.atan2(d[1], d[0]), 0.0]}
        if obs.get("offer"):
            a["pick"] = self._pick(obs["offer"], me)
        return a

    def _steer(self, pos, goal, vel, tick, track=True):
        """Navigation with straight-line fallback. Returns (move, jump, boost_hint)."""
        if self.nav_ok and self.nav is not None:
            try:
                res = self.nav.steer(pos, goal, self.cfg, vel, track)
                mv = _vec(res[0], 2)
                if mv is not None:
                    return mv, bool(res[1]), bool(res[2])
            except Exception as e:
                self.errs += 1
                if self.errs <= 5:
                    print("nav.steer failed:", repr(e), file=sys.stderr, flush=True)
        d = unit(goal[0] - pos[0], goal[1] - pos[1])
        return list(d), False, False

    def _los(self, a, b):
        if self.nav_ok and self.nav is not None:
            try:
                return bool(self.nav.los(a, b))
            except Exception:
                return True
        return True

    def _safe_point(self, center, radius, frm):
        if self.nav_ok and self.nav is not None:
            try:
                p = self.nav.safe_point(center, radius, frm)
                pv = _vec(p, 2)
                if pv is not None:
                    return pv
            except Exception:
                pass
        vx, vy = frm[0] - center[0], frm[1] - center[1]
        d = hyp(vx, vy)
        if d <= radius:
            return [frm[0], frm[1]]
        return [center[0] + vx / d * radius, center[1] + vy / d * radius]

    # ------------------------------------------------------------------ offers / loot values
    def _pick(self, offer, me):
        choices = offer.get("choices") or []
        if not choices:
            return 0
        have = {}
        for u in me.get("upgrades") or []:
            uid = u.get("id") if isinstance(u, dict) else u
            have[uid] = have.get(uid, 0) + 1
        held = {w.get("kind") for w in (me.get("weapons") or []) if isinstance(w, dict)}
        best, bi = -1e9, 0
        for i, c in enumerate(choices):
            cid = c.get("id") if isinstance(c, dict) else c
            s = UPGRADE_WEIGHT.get(cid, 3.0)
            s *= 1.0 - 0.12 * have.get(cid, 0)
            if cid == "lightning_efficiency" and "lightning" in held:
                s += 1
            if s > best:
                best, bi = s, i
        return bi

    def _enemy_fractions(self, t):
        n = 0
        c = {"laser": 0, "mortar": 0, "lightning": 0}
        for m in self.mem.values():
            if t - m["t"] <= 20:
                n += 1
                for k in m["weapons"]:
                    if k in c:
                        c[k] += 1
        return n, c

    def _weapon_value(self, kind, t):
        n, c = self._enemy_fractions(t)
        f = {k: (c[k] / n if n else 0.0) for k in c}
        if kind == "laser":
            return 3.0 + 1.5 * f["mortar"] - 2.0 * f["lightning"]
        if kind == "lightning":
            return 2.6 + 1.5 * f["laser"] - 1.0 * f["mortar"]
        if kind == "mortar":
            v = 2.0 + 1.5 * f["lightning"] - 3.0 * f["laser"]
            if c["laser"] > 0:
                v -= 2.5
            return v
        return 1.0

    # ------------------------------------------------------------------ main decision
    def _decide(self, obs):
        me = obs["self"]
        t = _num(obs.get("t"), 0.0)
        tick = obs.get("tick", 0)
        pos = _vec(me.get("pos"))
        vel = _vec(me.get("vel")) or [0.0, 0.0, 0.0]
        stats = me.get("stats") or {}
        hp = _num(me.get("hp"), 1.0)
        mhp = max(_num(me.get("max_hp"), 1400.0), 1.0)
        hpf = hp / mhp
        energy = _num(me.get("energy"), 0.0)
        maxe = _num(me.get("max_energy"), 100.0)
        walk = _num(stats.get("walk_speed"), _num(self.mech.get("walk_speed"), 11.7))
        aim_now = _vec(me.get("aim"), 2) or [0.0, 0.0]
        eye_h = _num(stats.get("eye_height"), 8.0)
        mz = _num(stats.get("muzzle_height"), 7.0)
        act = {"tick": tick}

        # ---- events
        take_blocked = False
        for ev in obs.get("events") or []:
            et = ev.get("type")
            if et == "damaged":
                if ev.get("weapon") != "zone":
                    self.prov_until = t + 4.0
                    b = ev.get("bearing")
                    if b is not None:
                        self.threat_bearing = _num(b)
                        self.threat_t = t
            elif et == "take_failed":
                self.bad[ev.get("id")] = t + 8.0
            elif et == "dropped":
                self.bad[ev.get("id")] = t + 30.0
        self.bad = {k: v for k, v in self.bad.items() if v > t}

        # ---- offers
        if obs.get("offer"):
            act["pick"] = self._pick(obs["offer"], me)

        # ---- world tracking
        mechs = [m for m in (obs.get("mechs") or []) if isinstance(m, dict) and _vec(m.get("pos"))]
        enemies, npcs = [], []
        for m in mechs:
            p = _vec(m["pos"])
            d = math.dist(p[:2], pos[:2])
            m["_d"] = d
            if m.get("kind") == "npc":
                npcs.append(m)
            else:
                enemies.append(m)
                self.mem[m.get("id")] = {"pos": p, "vel": _vec(m.get("vel")) or [0, 0, 0],
                                         "hp": _num(m.get("hp"), 1400.0), "weapons": list(m.get("weapons") or []),
                                         "t": t}
        enemies.sort(key=lambda m: m["_d"])
        npcs.sort(key=lambda m: m["_d"])
        self.mem = {k: v for k, v in self.mem.items() if t - v["t"] < 25}

        # sound danger (decayed, unit vectors weighted by loudness class)
        self.danger = [self.danger[0] * 0.85, self.danger[1] * 0.85]
        newest = None
        for s in obs.get("sounds") or []:
            k = s.get("kind")
            if k in ("gun", "laser", "laser_charge", "mortar", "explosion", "lightning"):
                w = {"near": 1.0, "mid": 0.5}.get(s.get("dist"), 0.2)
                b = _num(s.get("bearing"))
                self.danger[0] -= math.cos(b) * w   # stored as direction AWAY from fight
                self.danger[1] -= math.sin(b) * w
                if newest is None or w > newest[1]:
                    newest = (b, w)

        # ---- zone state
        zone = obs.get("zone") or {}
        cx, cy, cr = zone_now(zone, t)
        nc = _vec(zone.get("next_center"), 2) or [cx, cy]
        nr = _num(zone.get("next_radius"), cr)
        d_next = hyp(pos[0] - nc[0], pos[1] - nc[1])
        s_start = _num(zone.get("shrink_start"), 1e9)
        lead = max(0.0, d_next - nr * 0.6) / max(walk, 1.0) + 6.0
        phase_active = t >= s_start - lead
        inside_next = d_next < nr - 12
        inside_now = hyp(pos[0] - cx, pos[1] - cy) < cr - 6
        zone_urgent = (not me.get("in_zone", True)) or (not inside_now) or (phase_active and not inside_next)

        def zone_ok(p, margin=8.0):
            if phase_active:
                return hyp(p[0] - nc[0], p[1] - nc[1]) < nr - margin
            return hyp(p[0] - cx, p[1] - cy) < cr - margin - 10

        # anchor (hide point inside next circle, nearest to us)
        key = (round(nc[0]), round(nc[1]), round(nr))
        if key != self.anchor_key or t - self.anchor_t > 3.0:
            self.anchor = self._safe_point(nc, max(nr * 0.55, 3.0), pos)
            self.anchor_key, self.anchor_t = key, t
        anchor = self.anchor

        # ---- weapons
        wl = me.get("weapons") or []
        wk = {}
        for i, w in enumerate(wl[:2]):
            if isinstance(w, dict) and w.get("kind"):
                wk[w["kind"]] = (i, w)
        free_slot = next((i for i in (1, 0) if i < len(wl) and wl[i] is None), None)
        if len(wl) < 2:
            free_slot = None if len(wl) else 0

        # ---- threat evaluation
        vis = [e for e in enemies if e["_d"] < 160]
        n_close = len([e for e in vis if e["_d"] < 100])
        e0 = vis[0] if vis else None
        provoked = t < self.prov_until
        flee = False
        if e0:
            ehp = _num(e0.get("hp"), mhp)
            if n_close >= 3:
                flee = True
            elif hpf < 0.35 and ehp > 0.5 * hp:
                flee = True
            elif hpf < 0.55 and ehp > 1.3 * hp:
                flee = True
        if flee and e0 and e0["_d"] < 22 and hpf > 0.2 and n_close < 3:
            flee = False  # cornered at melee range: fight back

        # ---- dodge (projectiles, charging lasers, incoming mortar)
        dodge, dodge_w, dodge_jump = self._dodge(obs, pos, vel, t, enemies, stats)

        # ---- target selection
        target, ttype = None, None
        engaged = False
        if e0 and not zone_urgent or (e0 and provoked):
            pool = [e for e in vis if e["_d"] < 280]
            tgt = None
            if pool:
                def score(e):
                    s = e["_d"] - (30 if e.get("id") == self.target_id else 0)
                    s += 0.05 * _num(e.get("hp"), mhp)
                    return s
                tgt = min(pool, key=score)
            if tgt is not None:
                ehp_f = _num(tgt.get("hp"), mhp) / max(_num(tgt.get("max_hp"), mhp), 1)
                engaged = provoked or tgt["_d"] < 75 or (ehp_f < 0.4 and tgt["_d"] < 130) or bool(tgt.get("charging"))
                if engaged and (not flee or provoked):
                    target, ttype = tgt, "mech"
        farm_ok = (target is None and not flee and not zone_urgent and hpf > 0.6 and not vis)
        farm_target = None
        if farm_ok:
            for n in npcs:
                if n["_d"] < 60:
                    farm_target = n
                    break
            if farm_target is None:
                for c in obs.get("crates") or []:
                    cp = _vec(c.get("pos"))
                    if cp and hyp(cp[0] - pos[0], cp[1] - pos[1]) < 45 and zone_ok(cp):
                        farm_target = {"pos": cp, "vel": [0, 0, 0], "kind": "crate", "id": c.get("id"),
                                       "_d": hyp(cp[0] - pos[0], cp[1] - pos[1])}
                        break
            if farm_target is not None:
                target, ttype = farm_target, farm_target.get("kind", "npc")
        self.target_id = target.get("id") if target else None

        # ---- aiming / firing
        fire = [False, False]
        aim = None
        reload_now = False
        gun = wk.get("gun")
        if gun:
            gs = gun[1]
            mag = _num(_g(gs, "stats", "mag"), _num(_g(self.W, "gun", "mag"), 12))
            if _num(gs.get("reload"), 0) <= 0 and (_num(gs.get("ammo"), mag) <= 0 or (target is None and _num(gs.get("ammo"), mag) < mag * 0.6)):
                reload_now = True
        if target is not None:
            aim, fire = self._aim_fire(target, ttype, pos, mz, eye_h, aim_now, wk, energy, t)
        elif e0 is not None:
            aim = [math.atan2(e0["pos"][1] - pos[1], e0["pos"][0] - pos[0]), 0.0]   # face visible enemy (rear armor x1.5)
        elif self.threat_bearing is not None and t - self.threat_t < 2.5:
            aim = [self.threat_bearing, 0.0]   # face the attacker: rear armor x1.5
        elif newest is not None and newest[1] >= 0.5:
            aim = [newest[0], 0.0]
        if reload_now:
            act["reload"] = True

        # ---- weapon take / drop
        take_pickup = None
        goal = None
        mode = "hide"
        pickups = obs.get("pickups") or []
        hostile_near = bool(e0 and e0["_d"] < 40)
        best_pick, best_pv = None, 0.0
        if not zone_urgent or True:
            for p in pickups:
                pp = _vec(p.get("pos"))
                if not pp or p.get("id") in self.bad or p.get("kind") in (None, "gun") or p.get("kind") in wk:
                    continue
                dxy = hyp(pp[0] - pos[0], pp[1] - pos[1])
                dz = abs(pp[2] - pos[2])
                if dz > 6 or dxy > 90 or not zone_ok(pp, 4.0):
                    continue
                k = p["kind"]
                v = self._weapon_value(k, t)
                drop_slot = None
                if free_slot is None:
                    cands = [(self._weapon_value(kk, t), w[0], w[1]) for kk, w in wk.items() if kk != "gun"
                             and not _num(w[1].get("charge"), 0) > 0]
                    if not cands:
                        continue
                    worst = min(cands)
                    if v < worst[0] + 0.8:
                        continue
                    drop_slot = worst[1]
                    v -= worst[0]
                elif v < 1.8:
                    continue
                v = v - dxy * 0.02
                if v > best_pv:
                    best_pv, best_pick = v, (p, pp, dxy, dz, drop_slot)
        if best_pick and not hostile_near and not (flee or zone_urgent and best_pick[2] > 25):
            p, pp, dxy, dz, drop_slot = best_pick
            if dxy < self.pick_r - 0.6 and dz < 3.6:
                act["take"] = p["id"]
                if drop_slot is not None:
                    act["drop"] = drop_slot
            else:
                goal = (pp[0], pp[1])
                mode = "loot"
        # drop a mortar when a laser holder is in sight (cook-off), only if not taking
        if "take" not in act and "mortar" in wk and any("laser" in (e.get("weapons") or []) and e["_d"] < 260 for e in vis):
            act["drop"] = wk["mortar"][0]

        # ---- movement mode selection
        boost_pref = False
        d_goal = 0.0
        move_dir = None
        if zone_urgent:
            mode = "zone"
            goal = (anchor[0], anchor[1])
            boost_pref = (not me.get("in_zone", True)) or d_next > nr + 25
        elif flee and e0:
            mode = "flee"
            ax = ay = 0.0
            for e in vis[:4]:
                ux, uy = unit(pos[0] - e["pos"][0], pos[1] - e["pos"][1])
                w = 1.0 / max(e["_d"], 10.0)
                ax += ux * w
                ay += uy * w
            ax, ay = unit(ax, ay)
            gx, gy = unit(anchor[0] - pos[0], anchor[1] - pos[1])
            px, py = -ay, ax
            if t > self.strafe_until:
                self.strafe = -self.strafe
                self.strafe_until = t + 1.2 + 0.8 * ((tick * 7919) % 10) / 10
            mx, my = unit(ax * 1.0 + gx * 0.35 + px * 0.35 * self.strafe, ay * 1.0 + gy * 0.35 + py * 0.35 * self.strafe)
            move_dir = (mx, my)
            boost_pref = True
        elif target is not None and ttype in ("mech", "npc", "crate") and (engaged or farm_target is not None):
            mode = "fight" if ttype == "mech" else "farm"
            tp = _vec(target["pos"])
            d = target["_d"]
            pref = self._pref_range(target, wk, ttype)
            ux, uy = unit(tp[0] - pos[0], tp[1] - pos[1])
            px, py = -uy, ux
            if t > self.strafe_until:
                self.strafe = -self.strafe
                self.strafe_until = t + 1.0 + 1.2 * ((tick * 7919) % 10) / 10
            rad = max(-1.0, min(1.0, (d - pref) / 15.0))
            tang = 0.85 if ttype == "mech" else 0.3
            move_dir = unit(ux * rad + px * tang * self.strafe, uy * rad + py * tang * self.strafe)
            if hostile_near or d < 25:
                boost_pref = False
        elif goal is None:
            # cubes, supply drop, then hide
            safe_to_wander = not vis and hpf > 0.35 and not provoked
            drop = self._drop_goal(obs, pos, walk, zone_ok, enemies, hpf)
            if drop is not None and safe_to_wander:
                mode = "drop"
                goal = drop[0]
                if drop[1]:
                    move_dir = (0.0, 0.0)
                    goal = None
                boost_pref = drop[2]
            else:
                cube = None
                if safe_to_wander or (vis and e0["_d"] > 90 and hpf > 0.6):
                    best = 1e9
                    for c in obs.get("cubes") or []:
                        cp = _vec(c.get("pos"))
                        if not cp:
                            continue
                        dd = hyp(cp[0] - pos[0], cp[1] - pos[1])
                        if dd < 55 and abs(cp[2] - pos[2]) < 7 and zone_ok(cp, 4.0) and dd < best:
                            best, cube = dd, cp
                if cube is not None:
                    mode = "cube"
                    goal = (cube[0], cube[1])
                else:
                    mode = "hide"
                    da = hyp(anchor[0] - pos[0], anchor[1] - pos[1])
                    if da > 12:
                        goal = (anchor[0], anchor[1])
                        boost_pref = da > 90
                    else:
                        goal = None
                        ax, ay = self.danger
                        if hyp(ax, ay) > 1.5 and not vis:
                            move_dir = unit(ax, ay)
                            move_dir = (move_dir[0] * 0.6, move_dir[1] * 0.6)
                        else:
                            move_dir = (0.0, 0.0)
        else:
            boost_pref = False
        self.mode = mode

        # ---- compose movement
        jump = False
        steer_boost = False
        if goal is not None:
            mv, jump, steer_boost = self._steer(pos, goal, vel, tick)
            d_goal = hyp(goal[0] - pos[0], goal[1] - pos[1])
            if d_goal > 80 and energy > 55 and mode in ("zone", "hide", "drop", "loot", "cube"):
                boost_pref = True
            if d_goal < 6:
                s = d_goal / 6.0
                mv = [mv[0] * max(s, 0.25), mv[1] * max(s, 0.25)]
        elif move_dir is not None and hyp(*move_dir) > 0.05:
            mv, jump, steer_boost = self._steer(pos, (pos[0] + move_dir[0] * 40, pos[1] + move_dir[1] * 40), vel, tick, False)
            k = min(1.0, hyp(*move_dir))
            mv = [mv[0] * k, mv[1] * k]
        else:
            mv = [0.0, 0.0]
        if dodge_w > 0:
            if dodge_w >= 1.0:
                mv = [dodge[0], dodge[1]]
            else:
                mv = [mv[0] + dodge[0] * dodge_w * 1.5, mv[1] + dodge[1] * dodge_w * 1.5]
            jump = jump or dodge_jump
            boost_pref = boost_pref or dodge_w >= 1.0
        # laser charging: half speed anyway; no special handling

        # ---- boost hysteresis / energy reserve
        reserve = 28 if "lightning" in wk and engaged else 14
        if self.boost_on and energy < reserve - 6:
            self.boost_on = False
        elif not self.boost_on and energy > reserve + 22:
            self.boost_on = True
        urgent_out = not me.get("in_zone", True)
        want_boost = (boost_pref or steer_boost and mode == "zone") and hyp(*mv) > 0.2
        boost = bool(want_boost and (self.boost_on or (urgent_out and energy > 4)))
        if jump and not me.get("grounded", True):
            boost = boost or (energy > 20 and steer_boost)  # jet to clear ledges (nav hint)

        # nav stuck bookkeeping
        if self.nav_ok and self.nav is not None:
            try:
                self.nav.note_progress(pos, tick)
            except Exception:
                pass

        act["move"] = mv
        act["boost"] = boost
        act["jump"] = jump
        if aim is None:
            aim = [math.atan2(mv[1], mv[0]), 0.0] if hyp(*mv) > 0.2 else list(aim_now)
        act["aim"] = aim
        act["fire"] = fire
        act["debug"] = {"label": f"{mode} hp{hpf:.2f}"}
        return act

    # ------------------------------------------------------------------ pieces
    def _pref_range(self, target, wk, ttype):
        if ttype != "mech":
            return 28.0 if "lightning" in wk else 45.0
        tw = target.get("weapons") or []
        if "lightning" in wk:
            lr = _num(_g(wk["lightning"][1], "stats", "range"), 45.0)
            if "mortar" in tw:
                return lr * 1.9 if "gun" in wk else lr * 1.9   # mortar beats lightning: stay out
            return lr * 0.7
        if "laser" in wk:
            if "lightning" in tw:
                return 70.0       # lightning shorts us: keep out of its 45 m range
            return 95.0
        if "mortar" in wk:
            return 70.0 if "laser" not in tw else 40.0
        if "lightning" in tw:
            return 65.0
        return 70.0

    def _drop_goal(self, obs, pos, walk, zone_ok, enemies, hpf):
        best = None
        for d in obs.get("drops") or []:
            dp = _vec(d.get("pos"), 2)
            if not dp:
                continue
            r = _num(d.get("radius"), 8.0)
            lands = _num(d.get("lands_in"), 0.0)
            dist = hyp(dp[0] - pos[0], dp[1] - pos[1])
            if dist > 220 or not zone_ok(dp, 5.0):
                continue
            if (max(dist - r, 0) / max(walk, 1.0)) > lands + 14:
                continue
            contested = [e for e in enemies if hyp(e["pos"][0] - dp[0], e["pos"][1] - dp[1]) < r + 20]
            if contested and hpf < 0.7:
                continue
            holder = d.get("holder")
            me_id = _g(obs, "self", "id")
            if holder is not None and holder != me_id and len(contested) > 0 and hpf < 0.9:
                continue
            if best is None or dist < best[0]:
                inside = dist < r - 1.5 and lands <= 0
                best = (dist, (dp[0], dp[1]), inside, dist > 90)
        if best is None:
            return None
        return (best[1], best[2], best[3])

    def _dodge(self, obs, pos, vel, t, enemies, stats):
        """Return (dir, weight 0..1, jump)."""
        cx, cy, cz = pos[0], pos[1], pos[2] + 4.5
        dx = dy = 0.0
        w = 0.0
        jump = False
        grav = _num(_g(self.W, "mortar", "gravity"), 22.0)
        rad = _num(stats.get("radius"), 2.5)
        for p in obs.get("projectiles") or []:
            pp, pv = _vec(p.get("pos")), _vec(p.get("vel"))
            if not pp or not pv:
                continue
            rx, ry, rz = pp[0] - cx, pp[1] - cy, pp[2] - cz
            if p.get("kind") == "mortar":
                # time to descend to our height, then impact point
                a, b, c = -0.5 * grav, pv[2], pp[2] - pos[2]
                disc = b * b - 4 * a * c
                if disc < 0:
                    continue
                tl = (-b - math.sqrt(disc)) / (2 * a)
                if tl <= 0 or tl > 1.6:
                    continue
                ix, iy = pp[0] + pv[0] * tl - cx, pp[1] + pv[1] * tl - cy
                dist = hyp(ix, iy)
                blast = _num(_g(self.W, "mortar", "splash_radius"), 7.0) + 4.0
                if dist < blast:
                    ux, uy = unit(-ix, -iy)
                    if dist < 1e-6:
                        ux, uy = unit(-pv[0], -pv[1])
                    dx += ux * 1.5
                    dy += uy * 1.5
                    w = max(w, 1.0 if tl < 1.0 else 0.8)
                continue
            vx, vy = pv[0], pv[1]
            v2 = vx * vx + vy * vy + pv[2] * pv[2]
            if v2 < 1:
                continue
            tc = -(rx * pv[0] + ry * pv[1] + rz * pv[2]) / v2
            if tc < 0 or tc > 0.7:
                continue
            mx, my, mz = rx + pv[0] * tc, ry + pv[1] * tc, rz + pv[2] * tc
            miss = math.sqrt(mx * mx + my * my + mz * mz)
            if miss < rad + 2.2:
                ux, uy = unit(vx, vy)
                # sidestep perpendicular to travel, on the side away from the closest-approach offset
                side = mx * -uy + my * ux
                sgn = -1.0 if side >= 0 else 1.0
                dx += -uy * sgn
                dy += ux * sgn
                w = max(w, 0.7 if tc > 0.3 else 1.0)
        # charging lasers aimed at us
        for e in enemies:
            if not e.get("charging"):
                continue
            ep = e["pos"]
            d = e["_d"]
            if d > 300 or d < 1:
                continue
            ea = _vec(e.get("aim"), 2)
            if not ea:
                continue
            bearing = math.atan2(cy - ep[1], cx - ep[0])
            err = abs(wrap(bearing - ea[0]))
            if err < math.atan2(rad + 2.0, d) + 0.12:
                ux, uy = math.cos(ea[0]), math.sin(ea[0])
                side = (cx - ep[0]) * -uy + (cy - ep[1]) * ux
                sgn = 1.0 if side >= 0 else -1.0
                dx += -uy * sgn
                dy += ux * sgn
                w = max(w, 0.9)
                jump = True
        if w > 0:
            dx, dy = unit(dx, dy)
        return (dx, dy), w, jump

    def _aim_fire(self, target, ttype, pos, mz, eye_h, aim_now, wk, energy, t):
        tp = _vec(target["pos"])
        tv = _vec(target.get("vel")) or [0.0, 0.0, 0.0]
        scale = 1.0 + 0.05 * _num(target.get("cubes"), 0)
        center_h = 4.5 * scale if ttype == "mech" else (1.75 if ttype == "npc" else 1.2)
        tc = [tp[0], tp[1], tp[2] + center_h]
        d = math.dist(tp[:2], pos[:2])
        muzzle = [pos[0], pos[1], pos[2] + mz]
        eye = [pos[0], pos[1], pos[2] + eye_h]
        los = self._los(eye, tc)

        def aim_at(point):
            dh = hyp(point[0] - muzzle[0], point[1] - muzzle[1])
            return [math.atan2(point[1] - muzzle[1], point[0] - muzzle[0]), math.atan2(point[2] - muzzle[2], max(dh, 1e-6))]

        def err(a):
            return max(abs(wrap(a[0] - aim_now[0])), abs(a[1] - aim_now[1]))

        gun = wk.get("gun")
        laser = wk.get("laser")
        light = wk.get("lightning")
        mort = wk.get("mortar")
        fire = [False, False]

        def setf(kind, v):
            fire[wk[kind][0]] = bool(v)

        # --- choose primary weapon mode
        mode = "gun"
        if light and d <= _num(_g(light[1], "stats", "range"), 45.0) * 0.92 and energy >= 8 and los:
            mode = "lightning"
        elif laser and los and 10 < d <= _num(_g(laser[1], "stats", "range"), 280.0) - 6 and (
                _num(laser[1].get("charge"), 0) > 0 or _num(laser[1].get("cooldown"), 0) <= 0.7):
            mode = "laser"
        elif mort and 22 < d < 200 and _num(mort[1].get("cooldown"), 0) <= 0.6 and (not gun or d > 55 or not los):
            mode = "mortar"
        if mode == "gun" and not gun:
            mode = "none"

        # --- aim point per mode
        aim = None
        if mode in ("gun", "lightning", "none") or (mode == "laser" and d < 25):
            spd = _num(_g(gun[1], "stats", "speed"), 252.0) if gun else 252.0
            p, _ = lead_point(muzzle, tc, tv, spd)
            aim = aim_at(p)
            if mode == "lightning":
                aim = aim_at(tc)
        elif mode == "laser":
            p = [tc[i] + tv[i] * 0.1 for i in range(3)]   # hitscan fires within ~1 decision of release
            aim = aim_at(p)
        elif mode == "mortar":
            v = _num(_g(mort[1], "stats", "speed"), _num(_g(self.W, "mortar", "speed"), 72.0))
            g = _num(_g(mort[1], "stats", "gravity"), _num(_g(self.W, "mortar", "gravity"), 22.0))
            tube_z = pos[2] + eye_h + 1.5
            tt = d / v
            pitch = None
            for _ in range(4):
                px, py, pz = tp[0] + tv[0] * tt, tp[1] + tv[1] * tt, tp[2] + 1.0
                dh = hyp(px - pos[0], py - pos[1]) - 3.0
                pitch = mortar_pitch(dh, pz - tube_z, v, g)
                if pitch is None:
                    break
                tt = dh / max(v * math.cos(pitch), 1e-6)
            if pitch is None:
                mode = "gun" if gun else "none"
                p, _ = lead_point(muzzle, tc, tv, 252.0)
                aim = aim_at(p)
            else:
                aim = [math.atan2(py - pos[1], px - pos[0]), pitch]
        if aim is None:
            aim = aim_at(tc)
        e = err(aim)
        yaw_e = abs(wrap(aim[0] - aim_now[0]))

        # --- trigger discipline
        tol = max(0.02, math.atan2(2.0, max(d, 5.0)))
        if gun:
            gs = gun[1]
            gr = _num(_g(gs, "stats", "range"), 230.0)
            ok = (_num(gs.get("ammo"), 1) > 0 and _num(gs.get("reload"), 0) <= 0 and los and d < gr * 0.95)
            if mode in ("gun", "lightning") and ok and e < tol * 1.2:
                setf("gun", True)
            elif mode == "laser" and ok and d < 60 and e < tol:
                setf("gun", True)
        if light and mode == "lightning":
            cone = math.radians(_num(_g(light[1], "stats", "cone_deg"), 30.0))
            if yaw_e < cone * 0.35:
                setf("lightning", True)
        if mort and mode == "mortar" and e < 0.035:
            setf("mortar", True)
        if laser:
            lw = laser[1]
            ch = _num(lw.get("charge"), 0.0)
            full = _num(_g(lw, "stats", "charge"), _num(_g(self.W, "laser", "charge"), 0.75))
            if mode == "laser":
                if ch > 0:
                    # release when fully charged and lined up (or if it has overheld)
                    rel = (ch >= full - 0.05 and e < max(tol, 0.03)) or ch >= full + 0.8
                    setf("laser", not rel)
                else:
                    setf("laser", e < 0.25)
            else:
                setf("laser", False)   # release (or never start) when not in laser mode
        return aim, fire
