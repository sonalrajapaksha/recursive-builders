"""Policy self-checks. Run: python3 tests/test_policy.py  (also pytest-compatible). Uses a stub Nav."""
import copy
import gzip
import json
import math
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from policy import Policy, lead_point, mortar_pitch, zone_now  # noqa: E402


def load_stream():
    f = gzip.open(os.path.join(ROOT, "check", "stream.jsonl.gz"), "rt")
    hello = json.loads(f.readline())
    obs = [json.loads(l) for l in f if l.strip()]
    return hello, [o for o in obs if o.get("type") == "obs"]


class StubNav:
    def steer(self, pos, goal, cfg, vel=None, track=True):
        dx, dy = goal[0] - pos[0], goal[1] - pos[1]
        d = math.hypot(dx, dy) or 1.0
        return [dx / d, dy / d], False, False

    def los(self, a, b):
        return True

    def note_progress(self, pos, tick):
        return False

    def safe_point(self, c, r, frm):
        dx, dy = frm[0] - c[0], frm[1] - c[1]
        d = math.hypot(dx, dy)
        return [frm[0], frm[1]] if d <= r else [c[0] + dx / d * r, c[1] + dy / d * r]


HELLO, OBS = load_stream()


def mk(**kw):
    p = Policy(HELLO, StubNav())
    return p


def base_obs():
    o = copy.deepcopy(OBS[0])
    o["self"]["pos"] = [0.0, 0.0, 0.0]
    o["zone"] = {"center": [0, 0], "radius": 560, "next_center": [0, 0], "next_radius": 380,
                 "shrink_start": 60, "shrink_end": 110, "dps": 20}
    o["tick"], o["t"] = 100, 5.0
    return o


def enemy(id, x, y, hp=1400, weapons=("gun",), vel=(0, 0, 0), charging=False, aim=(0, 0)):
    return {"id": id, "kind": "mech", "pos": [x, y, 0.0], "vel": list(vel), "aim": list(aim), "hp": hp,
            "max_hp": 1400, "cubes": 0, "weapons": list(weapons), "charging": charging}


def valid(a, tick):
    assert a["tick"] == tick
    assert len(a["move"]) == 2 and math.hypot(*a["move"]) <= 1.0001
    assert all(math.isfinite(v) for v in a["move"] + a.get("aim", [0, 0]))
    assert len(a["fire"]) == 2 and all(isinstance(b, bool) for b in a["fire"])


def test_replay_valid_and_fast():
    p = mk()
    lat = []
    for o in OBS:
        t0 = time.perf_counter()
        a = p.act(o)
        lat.append((time.perf_counter() - t0) * 1000)
        valid(a, o["tick"])
    lat.sort()
    print(f"replay {len(lat)} obs: p50={lat[len(lat)//2]:.3f}ms p99={lat[int(len(lat)*.99)]:.3f}ms max={lat[-1]:.3f}ms")
    assert lat[int(len(lat) * .99)] < 15


def test_garbage_never_raises():
    p = mk()
    for o in [{}, {"tick": 5}, {"tick": 5, "self": {}}, {"tick": 7, "self": {"pos": None}},
              {"tick": 9, "self": {"pos": [0, 0, 0]}, "mechs": [None, {"pos": "x"}], "zone": None}, None]:
        a = p.act(o)
        assert "tick" in a and "move" in a


def test_lead_and_mortar_math():
    p, t = lead_point([0, 0, 0], [100, 0, 0], [0, 10, 0], 250)
    assert abs(p[1] - 10 * t) < 0.05 and abs(math.dist([0, 0, 0], p) / 250 - t) < 1e-3
    g, v = 22.0, 72.0
    for dh, dz in [(100, 0), (180, -5), (60, 8)]:
        th = mortar_pitch(dh, dz, v, g)
        x = y = 0.0
        tt = dh / (v * math.cos(th))
        yy = v * math.sin(th) * tt - 0.5 * g * tt * tt
        assert abs(yy - dz) < 0.01, (dh, dz, yy)
    assert mortar_pitch(300, 0, v, g) is None


def test_gun_fire_and_lead():
    p, o = mk(), base_obs()
    o["mechs"] = [enemy(3, 60, 0, vel=(0, 8, 0))]
    o["self"]["aim"] = [0.0, 0.0]
    a = p.act(o)
    assert a["aim"][1] != 0 or a["aim"][0] > 0, "should lead a target moving north"
    assert a["aim"][0] > 0.01
    # perfectly aligned static target -> fires
    o2 = base_obs()
    o2["mechs"] = [enemy(3, 60, 0)]
    o2["self"]["aim"] = [0.0, math.atan2(4.5 - 7, 57)]
    o2["self"]["aim"] = [0.0, -0.04]
    a2 = p.act(o2)
    assert a2["fire"][0] is True, a2


def test_no_fire_when_far_and_unprovoked():
    p, o = mk(), base_obs()
    o["mechs"] = [enemy(3, 150, 0)]
    a = p.act(o)
    assert a["fire"] == [False, False]


def test_flee_at_low_hp():
    p, o = mk(), base_obs()
    o["self"]["hp"] = 300
    o["mechs"] = [enemy(3, 50, 0, hp=1400)]
    a = p.act(o)
    assert a["move"][0] < -0.3, a   # runs away (west)
    assert a["boost"] is True or o["self"]["energy"] < 30


def test_dodge_bullet():
    p, o = mk(), base_obs()
    o["projectiles"] = [{"id": 1, "kind": "gun", "pos": [-40, 0.0, 4.5], "vel": [-250.0, 0, 0]}]
    o["projectiles"][0]["pos"] = [40, 0.3, 4.5]
    o["projectiles"][0]["vel"] = [-250.0, 0, 0]
    a = p.act(o)
    assert abs(a["move"][1]) > 0.8, a   # sidestep
    # bullet passing at y=+0.3 should push us to -y
    assert a["move"][1] < 0


def test_dodge_laser_charge():
    p, o = mk(), base_obs()
    o["mechs"] = [enemy(3, 100, 0, weapons=("gun", "laser"), charging=True, aim=(math.pi, 0))]
    a = p.act(o)
    assert abs(a["move"][1]) > 0.6 and a["jump"] is True, a


def test_dodge_mortar():
    p, o = mk(), base_obs()
    # shell landing ~2 m east of us in <1 s
    g = 22.0
    tl = 0.8
    vz = (0 - 20 + 0.5 * g * tl * tl) / tl
    o["projectiles"] = [{"id": 2, "kind": "mortar", "pos": [2 - 40 * tl, 0, 20], "vel": [40, 0, vz]}]
    a = p.act(o)
    assert a["move"][0] < -0.5, a


def test_zone_retreat_early():
    p, o = mk(), base_obs()
    o["self"]["pos"] = [300.0, 0.0, 0.0]
    o["t"] = 55.0     # shrink starts at 60; 300 m from center, next radius 380 but need to be well inside
    o["zone"]["next_center"] = [-100.0, 0.0]
    o["zone"]["next_radius"] = 100.0
    o["zone"]["radius"] = 560
    a = p.act(o)
    assert a["move"][0] < -0.8, a
    o["self"]["in_zone"] = False
    a = p.act(o)
    assert a["boost"] is True or o["self"]["energy"] < 5


def test_hide_inside_zone_stands_still():
    p, o = mk(), base_obs()
    a = p.act(o)
    assert math.hypot(*a["move"]) < 0.2, a


def test_offer_pick_prefers_armor():
    p, o = mk(), base_obs()
    o["offer"] = {"id": 1, "expires": 9, "choices": [{"id": "reactor"}, {"id": "gun_velocity"}, {"id": "armor"}]}
    assert p.act(o)["pick"] == 2
    o["offer"]["choices"] = [{"id": "laser_pierce"}, {"id": "capacitor"}, {"id": "mortar_splash"}]
    a = p.act(o)
    assert a["pick"] in (0, 1, 2)


def test_weapon_take_and_triangle():
    p, o = mk(), base_obs()
    o["pickups"] = [{"id": 8001, "kind": "laser", "pos": [1.0, 0.0, 0.0]}]
    a = p.act(o)
    assert a.get("take") == 8001, a
    # enemies hold lasers -> do not take mortar
    p2, o2 = mk(), base_obs()
    o2["mechs"] = [enemy(3, 140, 0, weapons=("gun", "laser"))]
    o2["pickups"] = [{"id": 8002, "kind": "mortar", "pos": [1.0, 0.0, 0.0]}]
    a2 = p2.act(o2)
    assert "take" not in a2, a2
    # both slots full: swap in lightning over mortar when lasers are about -> via value compare
    p3, o3 = mk(), base_obs()
    o3["self"]["weapons"][1] = {"kind": "mortar", "cooldown": 0, "stats": {"speed": 72}}
    o3["pickups"] = [{"id": 8003, "kind": "laser", "pos": [1.0, 0.0, 0.0]}]
    a3 = p3.act(o3)
    assert a3.get("take") == 8003 and a3.get("drop") == 1, a3


def test_failed_take_blacklisted():
    p, o = mk(), base_obs()
    o["pickups"] = [{"id": 8001, "kind": "laser", "pos": [1.0, 0.0, 0.0]}]
    o["events"] = [{"type": "take_failed", "id": 8001, "reason": "range"}]
    assert "take" not in p.act(o)


def test_laser_charge_release():
    p, o = mk(), base_obs()
    o["self"]["weapons"][1] = {"kind": "laser", "cooldown": 0, "charge": 0.0, "stats": {"charge": 0.75, "range": 280}}
    o["mechs"] = [enemy(3, 70, 0)]
    o["self"]["aim"] = [0.0, -0.04]
    a = p.act(o)
    assert a["fire"][1] is True      # start charging
    o["self"]["weapons"][1]["charge"] = 0.74
    a = p.act(o)
    assert a["fire"][1] is False     # release at full charge, aligned


def test_lightning_in_range_only():
    p, o = mk(), base_obs()
    o["self"]["weapons"][1] = {"kind": "lightning", "cooldown": 0, "stats": {"range": 45, "cone_deg": 30, "energy": 3}}
    o["mechs"] = [enemy(3, 30, 0)]
    o["self"]["aim"] = [0.05, 0]
    assert p.act(o)["fire"][1] is True
    o["mechs"] = [enemy(3, 60, 0)]
    assert p.act(o)["fire"][1] is False


def test_zone_now_interp():
    z = {"center": [0, 0], "radius": 100, "next_center": [50, 0], "next_radius": 50, "shrink_start": 10, "shrink_end": 20}
    assert zone_now(z, 5) == (0, 0, 100)
    assert zone_now(z, 15) == (25, 0, 75)
    assert zone_now(z, 25) == (50, 0, 50)


def test_nav_failure_fallback():
    class Bad:
        def steer(self, *a, **k): raise RuntimeError
        def los(self, *a): raise RuntimeError
        def note_progress(self, *a): raise RuntimeError
        def safe_point(self, *a): raise RuntimeError
    p = Policy(HELLO, Bad())
    for o in OBS[:50]:
        valid(p.act(o), o["tick"])
    p = Policy(HELLO, None)
    for o in OBS[:50]:
        valid(p.act(o), o["tick"])


def test_faces_visible_enemy_while_not_targeting():
    # enemy at 120 m (not engaged): we walk to the anchor but must keep facing it, not the walk direction
    o = base_obs()
    o["mechs"] = [enemy(5, 120, 0)]
    a = Policy(HELLO, StubNav()).act(o)
    assert not any(a["fire"]) and abs(a["aim"][0]) < 0.01, a


def test_strafe_steer_not_tracked_as_travel():
    calls = []

    class N(StubNav):
        def steer(self, pos, goal, cfg, vel=None, track=True):
            calls.append(track)
            return super().steer(pos, goal, cfg, vel)
    o = base_obs()
    o["mechs"] = [enemy(5, 50, 0)]
    Policy(HELLO, N()).act(o)
    assert calls and calls[0] is False, calls


def test_laser_lead_is_short():
    o = base_obs()
    o["self"]["weapons"][1] = {"kind": "laser", "cooldown": 0, "charge": 0,
                               "stats": HELLO["config"]["weapons"]["laser"]}
    o["mechs"] = [enemy(5, 60, 0, vel=(0, 10, 0))]
    o["self"]["aim"] = [0.0, 0.0]
    a = Policy(HELLO, StubNav()).act(o)
    # target moves 10 m/s: 0.1 s lead = 1 m => ~0.017 rad at 60 m (old 0.25 s lead = 0.042 rad)
    assert 0.0 < a["aim"][0] < 0.03, a["aim"]


def test_mortar_high_arc_when_blocked():
    lo = mortar_pitch(150, 0, 72, 22)
    hi = mortar_pitch(150, 0, 72, 22, True)
    assert lo < 0.5 < hi < 1.3
    assert mortar_pitch(60, 0, 72, 22, True) > 1.3   # too steep: policy must skip, not fire low into the wall

    class Blocked(StubNav):
        def los(self, a, b):
            return False
    o = base_obs()
    o["self"]["weapons"][1] = {"kind": "mortar", "cooldown": 0, "stats": HELLO["config"]["weapons"]["mortar"]}
    o["mechs"] = [enemy(5, 60, 0)]
    a = Policy(HELLO, Blocked()).act(o)
    assert not a["fire"][1], a
    o["mechs"] = [enemy(5, 150, 0)]
    o["events"] = [{"type": "damaged", "amount": 45, "weapon": "gun", "bearing": 0.0, "by": 5}]
    o["self"]["aim"] = [0.0, 0.5]
    a = Policy(HELLO, Blocked()).act(o)
    assert a["aim"][1] > 0.5, a


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("ok  ", name)
            except Exception as e:
                import traceback
                fails += 1
                print("FAIL", name, repr(e))
                traceback.print_exc()
    sys.exit(1 if fails else 0)
