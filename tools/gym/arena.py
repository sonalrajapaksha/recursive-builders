"""Multi-bot free-for-all simulator ("league") built on tools/sim.py.

Every one of the 16 mechs is driven by a bot instance that only sees what the protocol would show it
(vision wedge + near range, line of sight, sounds with bearing noise). Used to compare bot versions in
the same match (paired, mixed population) instead of against scripted house bots, which is closer to the
qualifying round / final (16 different teams' bots, no house bots).

Not the real game: no crates/NPC drones/upgrades/mortar/supply drops. Use it for relative comparisons.

Entry spec for tools/league.py:  LABEL=SPEC=COUNT
    SPEC = bot:<path>[?flag1,flag2]   one of our bot files (flags are exposed as bot.flags)
         | example                    the kit's example bot
         | hunter[:<noise_deg>]       naive aggressive bot (chase nearest, shoot, follow sounds)
"""
import copy
import importlib.util
import json
import math
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, 'lance'))
import sim as S  # noqa: E402

wrap = S.wrap
DT = S.DT


# ------------------------------------------------------------------------------------------------
# opponents
# ------------------------------------------------------------------------------------------------
class HunterBot:
    """Naive but competent-looking opponent: arms up, chases the nearest enemy it sees/hears, shoots."""
    name = "hunter"

    def __init__(self, hello, world=None, noise_deg=1.5):
        self.rng = random.Random(hello.get("seed", 0) * 7 + 1)
        self.noise = math.radians(noise_deg)
        self.w = world
        self.strafe = 1
        self.strafe_t = 0.0
        self.heard = None
        self.pref_mul = 1.0  # scales the preferred fighting distance (tools/practice.py --pref)

    def _slide(self, pos, mv):
        w = self.w
        if w is None or math.hypot(*mv) < 1e-6:
            return mv
        x, y, z = pos
        if not w.blocked(x + mv[0] * 4, y + mv[1] * 4, z, 4):
            return mv
        a0 = math.atan2(mv[1], mv[0])
        for da in (0.8, -0.8, 1.6, -1.6, 2.4, -2.4, 3.1):
            a2 = a0 + da
            if not w.blocked(x + math.cos(a2) * 4, y + math.sin(a2) * 4, z, 4):
                return [math.cos(a2), math.sin(a2)]
        return mv

    def act(self, obs):
        me = obs["self"]
        x, y, z = me["pos"]
        t = obs["t"]
        act = {"tick": obs["tick"]}
        held = [w["kind"] if w else None for w in me["weapons"]]
        want = [p for p in obs["pickups"] if p["kind"] in ("laser", "lightning") and p["kind"] not in held]
        near = [p for p in want if math.dist(p["pos"][:2], (x, y)) < 3.8]
        if near and None in held:
            act["take"] = near[0]["id"]
        enemies = [m for m in obs["mechs"] if m["kind"] == "mech"]
        tgt = min(enemies, key=lambda m: math.dist(m["pos"][:2], (x, y))) if enemies else None
        for s in obs["sounds"]:
            if s["kind"] in ("gun", "laser", "laser_charge", "lightning", "step", "boost") and s["dist"] != "far":
                self.heard = (t, s["bearing"])
        zn = obs["zone"]
        zc, zr = zn["center"], zn["radius"]
        nc = zn["next_center"]
        goal = None
        if math.dist((x, y), zc) > zr - 12 or (obs["t"] > zn["shrink_start"] - 15 and math.dist((x, y), nc) > zn["next_radius"] * 0.8):
            goal = nc
        move = [0.0, 0.0]
        aim = [me["aim"][0] + 0.3, 0.0]
        fire = [False, False]
        li = next((i for i, w in enumerate(me["weapons"]) if w and w["kind"] == "laser"), None)
        if tgt is not None:
            tp = tgt["pos"]
            d = math.dist(tp[:2], (x, y))
            ang = math.atan2(tp[1] - y, tp[0] - x)
            if t > self.strafe_t:
                self.strafe = -self.strafe
                self.strafe_t = t + 1 + self.rng.random() * 2
            if goal is None:
                pref = (70 if li is not None else 45) * self.pref_mul
                if d > pref + 15:
                    move = [math.cos(ang), math.sin(ang)]
                elif d < pref - 20:
                    move = [-math.cos(ang), -math.sin(ang)]
                else:
                    move = [math.cos(ang + 1.5708) * self.strafe, math.sin(ang + 1.5708) * self.strafe]
            tt = d / 252.0
            vel = tgt.get("vel", [0, 0, 0])
            px, py = tp[0] + vel[0] * tt, tp[1] + vel[1] * tt
            yaw = math.atan2(py - y, px - x) + self.rng.gauss(0, self.noise)
            pitch = math.atan2(tp[2] + 4.5 - z - 7, d) + self.rng.gauss(0, self.noise * 0.5)
            aim = [yaw, pitch]
            err = abs(wrap(yaw - me["aim"][0]))
            if d < 225 and err < 0.06:
                gi = next((i for i, w in enumerate(me["weapons"]) if w and w["kind"] == "gun"), None)
                if gi is not None:
                    fire[gi] = True
            zi = next((i for i, w in enumerate(me["weapons"]) if w and w["kind"] == "lightning"), None)
            if zi is not None and d < 42 and err < 0.2:
                fire[zi] = True
            if li is not None and d < 250:
                lw = me["weapons"][li]
                ch = lw.get("charge", 0) or 0
                if ch >= lw["stats"]["charge"] - 0.02 and err < 0.03:
                    fire[li] = False
                elif lw["cooldown"] <= 0.05 or ch > 0:
                    fire[li] = True
        else:
            if want:
                p = min(want, key=lambda q: math.dist(q["pos"][:2], (x, y)))
                if math.dist(p["pos"][:2], (x, y)) < 90 and goal is None:
                    goal = p["pos"][:2]
            if goal is None and self.heard and t - self.heard[0] < 4:
                b = self.heard[1]
                goal = (x + math.cos(b) * 60, y + math.sin(b) * 60)
            if goal is None and math.dist((x, y), nc) > zn["next_radius"] * 0.6:
                goal = nc
        if goal is not None and tgt is None:
            gd = math.hypot(goal[0] - x, goal[1] - y)
            if gd > 2:
                move = [(goal[0] - x) / gd, (goal[1] - y) / gd]
            aim = [math.atan2(move[1], move[0]) if gd > 2 else aim[0], 0.0]
        elif goal is not None and tgt is not None:
            gd = math.hypot(goal[0] - x, goal[1] - y) or 1.0
            move = [(goal[0] - x) / gd, (goal[1] - y) / gd]
        move = self._slide((x, y, z), move)
        act.update(move=move, aim=aim, fire=fire, boost=(not me["in_zone"]) and me["energy"] > 20,
                   jump=False)
        return act


class ExampleBot(S.ExampleBot):
    pass


# ------------------------------------------------------------------------------------------------
# league simulator
# ------------------------------------------------------------------------------------------------
class Prop(S.Mech):
    """Crate or NPC drone: a damageable thing that is not a player (never counted in placements)."""

    def __init__(self, pid, pos, kind, hp):
        super().__init__(pid, pos, 0.0, [None, None])
        self.kind = kind
        self.hp = self.max_hp = float(hp)
        self.home = list(pos)
        self.cubes = 0
        self.o_out = self.o_in = self.o_acc = 1.0
        self.o_vis = False
        self.armor = 0.0
        self.stats = {}
        self.cd = 0.0
        self.wt = 0.0
        self.wdir = (0.0, 0.0)


class League(S.Sim):
    def __init__(self, cfg, world, seed, entries, nav_cache=None, econ=False):
        """entries: list of 16 (label, factory) with factory(hello, world) -> bot instance."""
        self.cfg, self.w, self.rng = cfg, world, random.Random(seed)
        self.t = 0.0
        self.zone_phase = 0
        z = cfg["zone"]
        self.z_center, self.z_radius = list(z["start_center"]), z["start_radius"]
        self.z_next = self._next_circle()
        self.z_phase_start = 0.0
        spawns = self._spawns(16)
        self.mechs = []
        for i in range(16):
            m = S.Mech(i, spawns[i], 1.0, [S.weapon("gun", cfg), None])
            m.cubes = 0
            m.label = entries[i][0]
            m.step_t = 0.0
            m.act_ms = []
            m.cpu_ms = []
            m.stats = {}
            m.upg = {}
            m.offer = None
            m.offer_q = 0
            m.offer_n = 0
            m.thr_i = 0
            m.armor = 0.0
            m.regen_mul = 1.0
            m.regen_delay = float(cfg["mech"]["regen_delay"])
            self.mechs.append(m)
        self.pickups = []
        for k in range(40):
            p = self._open_point(self.z_center, self.z_radius * 0.9)
            self.pickups.append({"id": 8000 + k, "kind": self.rng.choice(["mortar", "laser", "lightning"]), "pos": p})
        self.bullets = []
        self.cubes = []
        self.deaths = []
        self.econ = econ
        self.props = []
        self.drops = []
        self.drops_called = set()
        self.thr = cfg["cubes"]["upgrade_thresholds"]
        if econ:
            for k in range(27):  # 36 crates in the real game, a quarter on roofs (not modelled)
                self.props.append(Prop(1000 + k, self._open_point(self.z_center, self.z_radius * 0.9), "crate", 300))
            for k in range(12):
                self.props.append(Prop(100 + k, self._open_point(self.z_center, self.z_radius * 0.8), "npc", 350))
        self.evs = {i: [] for i in range(16)}
        self.snd_buf = []
        self.snd_prev = []
        self.bots = []
        for i in range(16):
            hello = {"type": "hello", "protocol": "mechfight/1", "slot": i, "seed": seed * 100 + i,
                     "map": {"dir": "", "files": []}, "config": cfg}
            self.bots.append(entries[i][1](hello, world))
        self.errors = 0
        self._kind = "gun"
        self.deaths_t = {}
        # --- oracle switches (upper-bound experiments; a bot's flags o_* grant the mech a capability)
        for m, bot in zip(self.mechs, self.bots):
            fl = getattr(bot, "flags", set())
            m.o_acc = 1.5 if "o_acc" in fl else 1.0      # hit boxes (bullets, laser) 1.5x wider
            m.o_in = 0.7 if "o_dmgin" in fl else 1.0     # takes 30% less damage
            m.o_out = 1.3 if "o_dmgout" in fl else 1.0   # deals 30% more damage
            m.o_vis = "o_vis" in fl                      # 360 deg vision to 300 m, hearing x1.5 with half the noise
            if "o_hp" in fl:
                m.hp = m.max_hp = 1400.0 * 1.3
            for tag, n in (("o_cubes5", 5), ("o_cubes10", 10), ("o_cubes15", 15)):
                if tag in fl:
                    self._give_cubes(m, n)

    # ---------------------------------------------------------------- sounds
    def _sound(self, kind, m):
        self.snd_buf.append((kind, (m.pos[0], m.pos[1], m.pos[2]), m.id))

    def _stat(self, m, key, v=1):
        m.stats[key] = m.stats.get(key, 0) + v

    def shoot_bullet(self, m, s):
        self._sound("gun", m)
        self._stat(m, "gun_shots")
        super().shoot_bullet(m, s)

    def fire_laser(self, m, s, ev):
        self._sound("laser", m)
        self._stat(m, "laser_shots")
        self._kind = "laser"
        try:
            self._fire_laser_impl(m, s, ev)
        finally:
            self._kind = "gun"

    def _fire_laser_impl(self, m, s, ev):
        frac = s["min_frac"] + (1 - s["min_frac"]) * min(1.0, m.charge / s["charge"])
        m.charge = 0.0
        w = [x for x in m.weapons if x and x["kind"] == "laser"][0]
        w["charge"], w["cooldown"] = 0.0, s["cooldown"]
        yaw, pitch = m.aim
        d = (math.cos(pitch) * math.cos(yaw), math.cos(pitch) * math.sin(yaw), math.sin(pitch))
        o = (m.pos[0], m.pos[1], m.pos[2] + 7)
        best = None
        for t in self.targets(m):
            rel = [t.pos[0] - o[0], t.pos[1] - o[1]]
            along = rel[0] * d[0] + rel[1] * d[1]
            if along <= 0 or along > s["range"]:
                continue
            perp = abs(rel[0] * d[1] - rel[1] * d[0])
            hz = o[2] + d[2] * along / max(1e-6, math.hypot(d[0], d[1]))
            sc = 1.0 + 0.05 * t.cubes
            if perp < 2.5 * m.o_acc * sc and t.pos[2] - 0.5 <= hz <= t.pos[2] + 9.5 * sc:
                if self.w.los(o, (t.pos[0], t.pos[1], hz)) and (best is None or along < best[0]):
                    best = (along, t)
        if best:
            self.damage(best[1], m, s["damage"] * frac, ev)

    def step_bullets(self, ev):
        keep = []
        for b in self.bullets:
            alive = True
            shooter = self.mechs[b["by"]]
            rad = 2.8 * shooter.o_acc
            for _ in range(4):
                o = list(b["pos"])
                for i in range(3):
                    b["pos"][i] += b["vel"][i] * DT / 4
                b["left"] -= math.dist(o, b["pos"])
                if b["left"] <= 0 or not self.w.los(o, b["pos"], 2.0):
                    alive = False
                    break
                hit = None
                for t in self.targets(shooter):
                    px, py = t.pos[0], t.pos[1]
                    if abs(px - o[0]) > 30 or abs(py - o[1]) > 30:
                        continue
                    sx, sy = b["pos"][0] - o[0], b["pos"][1] - o[1]
                    L = sx * sx + sy * sy or 1e-9
                    u = max(0.0, min(1.0, ((px - o[0]) * sx + (py - o[1]) * sy) / L))
                    cx, cy, cz = o[0] + sx * u, o[1] + sy * u, o[2] + (b["pos"][2] - o[2]) * u
                    sc = 1.0 + 0.05 * t.cubes
                    if math.hypot(cx - px, cy - py) < rad * sc and t.pos[2] - 0.3 <= cz <= t.pos[2] + 9.3 * sc:
                        hit = t
                        break
                if hit:
                    self.damage(hit, shooter, b["dmg"], ev)
                    alive = False
                    break
            if alive:
                keep.append(b)
        self.bullets = keep

    def fire_lightning(self, m, s, ev):
        self._sound("lightning", m)
        self._stat(m, "light_shots")
        self._kind = "lightning"
        try:
            super().fire_lightning(m, s, ev)
        finally:
            self._kind = "gun"

    def apply(self, m, a, events_for):
        if not m.alive:
            return
        prev_charge = m.charge
        super().apply(m, a, events_for)
        if m.charge > 0 and prev_charge == 0:
            self._sound("laser_charge", m)
        sp = math.hypot(m.vel[0], m.vel[1])
        if m.grounded and sp > self.cfg["sound"]["step_speed"] and self.t >= m.step_t:
            self._sound("boost" if a.get("boost") and m.energy > 0 else "step", m)
            m.step_t = self.t + self.cfg["sound"]["step_every"]

    # ---------------------------------------------------------------- combat rules (everyone fights everyone)
    def targets(self, m):
        if isinstance(m, Prop):
            return []
        res = [x for x in self.mechs if x.alive and x is not m]
        if self.props:
            res += [q for q in self.props if q.alive]
        return res

    def damage(self, t, by, amt, ev):
        self._stat(by, {"gun": "gun_hits", "laser": "laser_hits", "lightning": "light_hits"}[self._kind])
        self._stat(by, "dmg_out", amt)
        self._stat(t, "dmg_in", amt)
        amt *= (1 + 0.04 * min(by.cubes, 10)) * by.o_out * t.o_in * (1.0 - t.armor)
        to_by = math.atan2(by.pos[1] - t.pos[1], by.pos[0] - t.pos[0])
        rear = (not isinstance(t, Prop)) and abs(wrap(to_by - t.aim[0])) > math.pi / 2
        if rear:
            amt *= 1.5
        t.hp -= amt
        t.last_dmg = self.t
        by.last_dmg = self.t
        wname = "npc" if isinstance(by, Prop) else "gun"
        if t.id in self.evs:
            self.evs[t.id].append({"type": "damaged", "amount": amt, "weapon": wname, "bearing": to_by, "by": by.id, "rear": rear})
        if by.id in self.evs:
            self.evs[by.id].append({"type": "hit", "target": t.id, "amount": amt, "weapon": "gun"})
        if t.hp <= 0 and t.alive:
            self._die(t, by)

    def _die(self, t, by):
        if isinstance(t, Prop):
            t.alive = False
            for k in range(1 if t.kind == "crate" else 2):
                self.cubes.append({"id": 5000 + len(self.cubes) + k + int(self.t * 10), "pos": [t.pos[0] + k * 2 - 1, t.pos[1], t.pos[2]]})
            if t.kind == "crate":
                self._sound("crate", t)
                if self.rng.random() < 0.5:
                    self.pickups.append({"id": 9800 + t.id, "kind": self.rng.choice(["mortar", "laser", "lightning"]), "pos": list(t.pos)})
            return
        t.alive = False
        self.deaths.append((self.t, t.id))
        self.deaths_t[t.id] = self.t
        self._sound("death", t)
        for k in range(2 + t.cubes):
            self.cubes.append({"id": 5000 + len(self.cubes) + k + int(self.t * 10),
                               "pos": [t.pos[0] + (k % 3) * 2 - 2, t.pos[1] + (k // 3) * 2, t.pos[2]]})
        if by is not None and by.id in self.evs:
            self.evs[by.id].append({"type": "kill", "target": t.id})
        for w in t.weapons:
            if w and w["kind"] != "gun":
                self.pickups.append({"id": 9500 + t.id * 3 + len(self.pickups), "kind": w["kind"], "pos": list(t.pos)})

    # ---------------------------------------------------------------- economy
    def _recalc_hp(self, m):
        new_max = 1400.0 * (1.15 ** m.upg.get("plating", 0)) * (1 + 0.04 * min(m.cubes, 10))
        if "o_hp" in getattr(self.bots[m.id], "flags", set()):
            new_max *= 1.3
        if new_max > m.max_hp:
            m.hp += new_max - m.max_hp
        m.max_hp = new_max

    def _give_cubes(self, m, n):
        m.cubes += n
        self._recalc_hp(m)
        while m.thr_i < len(self.thr) and m.cubes >= self.thr[m.thr_i]:
            m.offer_q += 1
            m.thr_i += 1
        self.evs[m.id].append({"type": "pickup", "cubes": m.cubes})

    def _offer_tick(self, m, pick):
        if m.offer is None and m.offer_q > 0:
            avail = [u for u in self.cfg["upgrades"] if m.upg.get(u["id"], 0) < u["max"] and
                     (("requires" not in u) or any(w and w["kind"] == u["requires"] for w in m.weapons))]
            ch = self.rng.sample(avail, min(3, len(avail)))
            m.offer = {"id": m.offer_n, "expires": round(self.t + 5.0, 2),
                       "choices": [{"id": u["id"], "name": u["name"], "desc": u["desc"]} for u in ch]}
            m.offer_n += 1
            m.offer_q -= 1
            return
        if m.offer is not None:
            n = len(m.offer["choices"])
            if isinstance(pick, int) and 0 <= pick < n:
                idx = pick
            elif self.t >= m.offer["expires"]:
                idx = 0
            else:
                return
            uid = m.offer["choices"][idx]["id"]
            m.upg[uid] = m.upg.get(uid, 0) + 1
            if uid == "plating":
                self._recalc_hp(m)
            elif uid == "armor":
                m.armor += 0.08
            elif uid == "nanites":
                m.regen_mul *= 1.6
                m.regen_delay -= 1.5
            self.evs[m.id].append({"type": "upgrade", "id": uid})
            m.offer = None

    def _econ_step(self, alive):
        cfg = self.cfg
        # NPC drones wander near home and shoot at mechs within 45 m
        for p in self.props:
            if not p.alive or p.kind != "npc":
                continue
            p.wt -= DT
            if p.wt <= 0:
                if self.rng.random() < 0.3:
                    p.wdir = (0.0, 0.0)
                else:
                    a = self.rng.random() * math.tau
                    p.wdir = (math.cos(a), math.sin(a))
                p.wt = 1.0 + 2.0 * self.rng.random()
            nx, ny = p.pos[0] + p.wdir[0] * 5.0 * DT, p.pos[1] + p.wdir[1] * 5.0 * DT
            if math.dist((nx, ny), p.home[:2]) < 30 and not self.w.blocked(nx, ny, p.pos[2], 1.5):
                p.pos = [nx, ny, self.w.ground(nx, ny)]
            p.cd -= DT
            if p.cd <= 0:
                best, bd = None, 45.0
                for m in alive:
                    d = math.dist(m.pos[:2], p.pos[:2])
                    if d < bd and self.w.los((p.pos[0], p.pos[1], p.pos[2] + 3), (m.pos[0], m.pos[1], m.pos[2] + 4.5), 3.0):
                        best, bd = m, d
                if best is not None:
                    p.cd = 1.0
                    if self.rng.random() < 0.6:
                        self._kind = "gun"
                        self.damage(best, p, 25.0, None)
        # supply drops
        dr = cfg["drops"]
        for k, tt in enumerate(dr["times"]):
            if self.t >= tt and k not in self.drops_called:
                self.drops_called.add(k)
                nc, nr = self.z_next
                pos = self._open_point(nc, max(10.0, nr * 0.7))
                self.drops.append({"id": 20000 + k, "pos": pos, "land": self.t + dr["fall_s"], "progress": 0.0, "holder": None})
        for d in list(self.drops):
            if self.t < d["land"]:
                continue
            inside = [m for m in alive if m.alive and math.dist(m.pos[:2], d["pos"][:2]) <= dr["radius"]]
            if len(inside) == 1:
                if d["holder"] == inside[0].id:
                    d["progress"] += DT
                else:
                    d["holder"], d["progress"] = inside[0].id, DT
            else:
                d["holder"], d["progress"] = None, 0.0
            if d["progress"] >= dr["capture_s"] and d["holder"] is not None:
                m = self.mechs[d["holder"]]
                self._give_cubes(m, dr["cubes"])
                m.hp, m.energy = m.max_hp, 100.0
                self.evs[m.id].append({"type": "drop", "id": d["id"], "cubes": m.cubes})
                self.drops.remove(d)

    # ---------------------------------------------------------------- observations
    def _los_cached(self, a, b, cache):
        key = (a.id, b.id) if a.id < b.id else (b.id, a.id)
        r = cache.get(key)
        if r is None:
            r = self.w.los((a.pos[0], a.pos[1], a.pos[2] + 8), (b.pos[0], b.pos[1], b.pos[2] + 8))
            cache[key] = r
        return r

    def obs_for(self, me, los_cache):
        t = self.t
        eye = (me.pos[0], me.pos[1], me.pos[2] + 8)
        mechs = []
        for m in self.mechs:
            if m is me or not m.alive:
                continue
            d = math.dist(m.pos[:2], me.pos[:2])
            seen = False
            if d <= (300 if me.o_vis else 200):
                ok = True
                if d > 45 and not me.o_vis:
                    ang = math.atan2(m.pos[1] - me.pos[1], m.pos[0] - me.pos[0])
                    ok = abs(wrap(ang - me.aim[0])) <= math.radians(60)
                if ok and self._los_cached(me, m, los_cache):
                    seen = True
            if seen:
                me.seen[m.id] = t
            if t - me.seen.get(m.id, -99) <= 5:
                mechs.append({"id": m.id, "kind": "mech", "pos": list(m.pos), "vel": list(m.vel), "aim": list(m.aim),
                              "hp": m.hp, "max_hp": m.max_hp, "cubes": m.cubes,
                              "weapons": [w["kind"] for w in m.weapons if w], "charging": m.charge > 0})

        for q in self.props:
            if q.alive and q.kind == "npc" and math.dist(q.pos[:2], me.pos[:2]) <= (300 if me.o_vis else 200):
                ang = math.atan2(q.pos[1] - me.pos[1], q.pos[0] - me.pos[0])
                if (math.dist(q.pos[:2], me.pos[:2]) <= 45 or me.o_vis or abs(wrap(ang - me.aim[0])) <= math.radians(60)) and \
                        self.w.los(eye, (q.pos[0], q.pos[1], q.pos[2] + 2.0), 3.0):
                    mechs.append({"id": q.id, "kind": "npc", "pos": list(q.pos), "vel": [q.wdir[0] * 5.0, q.wdir[1] * 5.0, 0.0],
                                  "aim": [0.0, 0.0], "hp": q.hp, "max_hp": q.max_hp})

        def vis_point(p, near=45):
            d = math.dist(p[:2], me.pos[:2])
            if d > (300 if me.o_vis else 200):
                return False
            if d > near and not me.o_vis and abs(wrap(math.atan2(p[1] - me.pos[1], p[0] - me.pos[0]) - me.aim[0])) > math.radians(60):
                return False
            return self.w.los(eye, (p[0], p[1], p[2] + 1.0), 3.0)

        pick = [p for p in self.pickups if math.dist(p["pos"][:2], me.pos[:2]) < 200 and vis_point(p["pos"])]
        cubes = [dict(c) for c in self.cubes if math.dist(c["pos"][:2], me.pos[:2]) < 200 and vis_point(c["pos"])]
        crates = [{"id": q.id, "pos": list(q.pos), "hp": q.hp} for q in self.props
                  if q.alive and q.kind == "crate" and math.dist(q.pos[:2], me.pos[:2]) < 200 and vis_point(q.pos)]
        drops = [{"id": d["id"], "pos": list(d["pos"]), "radius": self.cfg["drops"]["radius"],
                  "lands_in": round(max(0.0, d["land"] - t), 2), "capture_s": self.cfg["drops"]["capture_s"],
                  "progress": round(d["progress"], 2), "holder": d["holder"]} for d in self.drops]
        projs = []
        for b in self.bullets:
            if b["by"] != me.id and math.dist(b["pos"][:2], me.pos[:2]) < 110:
                ang = math.atan2(b["pos"][1] - me.pos[1], b["pos"][0] - me.pos[0])
                if math.dist(b["pos"][:2], me.pos[:2]) < 45 or abs(wrap(ang - me.aim[0])) <= math.radians(60):
                    projs.append({"id": 1, "kind": "gun", "pos": [round(v, 2) for v in b["pos"]],
                                  "vel": [round(v, 2) for v in b["vel"]]})
        sounds = []
        rng_tab = self.cfg["sound"]["range"]
        sig = math.radians(self.cfg["sound"]["bearing_noise_deg"]) * (0.5 if me.o_vis else 1.0)
        for kind, pos, src in self.snd_prev:
            if src == me.id:
                continue
            d = math.dist(pos[:2], me.pos[:2])
            if d <= rng_tab.get(kind, 100) * (1.5 if me.o_vis else 1.0):
                sounds.append({"kind": kind, "bearing": wrap(math.atan2(pos[1] - me.pos[1], pos[0] - me.pos[0]) + self.rng.gauss(0, sig)),
                               "dist": "near" if d < 60 else ("mid" if d < 160 else "far"), "age": 0.05})
        c, r, dps = self.zone_now()
        ss, se, _ = self.zone_info()
        events, self.evs[me.id] = self.evs[me.id], []
        return {"type": "obs", "tick": int(round(t * 20)), "t": round(t, 2),
                "alive": sum(m.alive for m in self.mechs),
                "self": {"id": me.id, "pos": list(me.pos), "vel": list(me.vel), "aim": list(me.aim), "hp": me.hp,
                         "max_hp": round(me.max_hp, 1), "energy": me.energy, "max_energy": 100, "grounded": me.grounded,
                         "cubes": me.cubes, "upgrades": [u for u, n in me.upg.items() for _ in range(n)], "in_zone": math.dist(me.pos[:2], c) <= r,
                         "weapons": copy.deepcopy(me.weapons), "stats": dict(self.cfg["mech"])},
                "mechs": mechs, "projectiles": projs, "crates": crates, "cubes": cubes, "pickups": pick,
                "sounds": sounds, "beams": [], "events": events, "drops": drops,
                "zone": {"center": c, "radius": r, "next_center": self.z_next[0], "next_radius": self.z_next[1],
                         "shrink_start": ss, "shrink_end": se, "dps": dps},
                "offer": me.offer}

    # ---------------------------------------------------------------- main loop
    def run(self, max_t=480):
        cfg = self.cfg["mech"]
        while self.t < max_t:
            alive = [m for m in self.mechs if m.alive]
            if len(alive) <= 1:
                break
            self.snd_prev, self.snd_buf = self.snd_buf, []
            cache = {}
            acts = {}
            # two phases so subprocess bots (procbot.py) think in parallel: send all obs, then collect all actions
            pend = {}
            for m in alive:
                o = self.obs_for(m, cache)
                bot = self.bots[m.id]
                t0 = time.perf_counter()
                c0 = time.thread_time()
                if hasattr(bot, "begin"):
                    bot.begin(o)
                    pend[m.id] = (t0, c0, None)
                else:
                    try:
                        a = bot.act(o) or {}
                    except Exception as e:  # a crashing bot idles, like the real wrapper falls back to the last action
                        self.errors += 1
                        if self.errors <= 3:
                            print("bot error", m.label, repr(e), file=sys.stderr)
                        a = {}
                    m.act_ms.append((time.perf_counter() - t0) * 1000)
                    m.cpu_ms.append((time.thread_time() - c0) * 1000)
                    acts[m.id] = a
            for m in alive:
                if m.id in pend:
                    t0, c0, _ = pend[m.id]
                    a = self.bots[m.id].collect() or {}
                    m.act_ms.append(self.bots[m.id].last_ms)
                    m.cpu_ms.append(0.0)
                    acts[m.id] = a
            for m in alive:
                self.apply(m, acts[m.id], None)
            self.step_bullets(None)
            if self.econ:
                self._econ_step(alive)
            for m in alive:
                if m.alive:
                    self._offer_tick(m, acts[m.id].get("pick"))
            for cb in list(self.cubes):
                best, bd = None, 3.5
                for m in alive:
                    if m.alive and abs(cb["pos"][2] - m.pos[2]) < 4:
                        d = math.dist(cb["pos"][:2], m.pos[:2])
                        if d < bd:
                            best, bd = m, d
                if best is not None:
                    self.cubes.remove(cb)
                    self._give_cubes(best, 1)
            c, r, dps = self.zone_now()
            for m in self.mechs:
                if not m.alive:
                    continue
                if math.dist(m.pos[:2], c) > r:
                    m.hp -= dps * DT
                    m.last_dmg = self.t
                    self.evs[m.id].append({"type": "damaged", "amount": dps * DT, "weapon": "zone", "bearing": None, "by": None})
                    if m.hp <= 0:
                        self._die(m, None)
                elif self.t - m.last_dmg > m.regen_delay:
                    m.hp = min(m.max_hp, m.hp + cfg["regen_per_s"] * m.regen_mul * DT)
            self.step_zone()
            self.t += DT
        return self.results()

    def results(self):
        surv = sorted((m for m in self.mechs if m.alive), key=lambda m: -m.hp)
        place = {}
        for i, m in enumerate(surv):
            place[m.id] = i + 1
        dead_order = [i for t, i in self.deaths]  # first to die first
        nxt = len(surv) + 1
        for i in reversed(dead_order):
            if i not in place:
                place[i] = nxt
                nxt += 1
        out = []
        for m in self.mechs:
            m.stats["cubes"] = m.cubes
            m.stats["plating"] = m.upg.get("plating", 0)
            m.stats["armor_up"] = m.upg.get("armor", 0)
            ms = sorted(m.act_ms)
            cs = sorted(m.cpu_ms)
            out.append({"cpu_p99": round(cs[int(len(cs) * 0.99)], 2) if cs else 0, "cpu_max": round(cs[-1], 2) if cs else 0,
                        "id": m.id, "label": m.label, "place": place[m.id], "points": 16 - place[m.id],
                        "act_p99": round(ms[int(len(ms) * 0.99)], 2) if ms else 0, "act_max": round(ms[-1], 2) if ms else 0,
                        "stats": dict(m.stats), "alive_s": round(self.deaths_t.get(m.id, self.t), 1)})
        return out


# ------------------------------------------------------------------------------------------------
# entry factories
# ------------------------------------------------------------------------------------------------
_MODS = {}


def load_bot_module(path):
    path = os.path.abspath(path)
    if path in _MODS:
        return _MODS[path]
    spec = importlib.util.spec_from_file_location("botmod_%d" % len(_MODS), path)
    mod = importlib.util.module_from_spec(spec)
    old = list(sys.path)
    sys.path.insert(0, os.path.dirname(path))
    sys.path.insert(0, os.path.join(HERE, 'lance'))  # for mechfight.py
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path[:] = old
    _MODS[path] = mod
    return mod


def make_factory(spec, kit):
    """Returns factory(hello, world) -> bot instance."""
    if spec == "example":
        return lambda hello, world: ExampleBot(hello)
    if spec.startswith("hunter"):
        noise = float(spec.split(":")[1]) if ":" in spec else 1.5
        return lambda hello, world: HunterBot(hello, world, noise)
    assert spec.startswith("bot:"), spec
    path, _, flags = spec[4:].partition("?")
    flagset = set(f for f in flags.split(",") if f)
    mod = load_bot_module(path)
    if not hasattr(mod, "_shared"):
        w = mod.World(os.path.join(kit, "arena"))
        nav = mod.Nav(w) if hasattr(mod, "Nav") and w.ok else None
        mod._shared = (w, nav)
        mod.World = lambda _d, _w=w: _w
        if nav is not None:
            mod.Nav = lambda _w, _n=nav: _n

    def factory(hello, world):
        inst = mod.Bot(hello)
        inst.flags = flagset
        return inst
    return factory


def load_cfg(kit):
    import gzip
    with gzip.open(os.path.join(kit, "check", "stream.jsonl.gz"), "rt") as f:
        return json.loads(f.readline())["config"]
