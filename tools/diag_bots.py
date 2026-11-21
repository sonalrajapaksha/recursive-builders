"""Opponent/own-damage diagnostics from a recorded stream (stdlib only).
Usage: python3 -I tools/diag_bots.py [check/stream.jsonl.gz]   (report on stdout)
"""
import collections
import gzip
import json
import math
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(path):
    f = gzip.open(path, "rt") if path.endswith(".gz") else open(path)
    hello = json.loads(f.readline())
    obs = [o for o in (json.loads(l) for l in f if l.strip()) if o.get("type") == "obs"]
    return hello, obs


def wrap(a):
    return (a + math.pi) % math.tau - math.pi


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))] if v else float("nan")


def analyse(hello, obs):
    cfg = hello.get("config", {})
    walk = cfg.get("mech", {}).get("walk_speed", 11.7)
    boost = cfg.get("mech", {}).get("boost_speed", 19.5)
    tr = {}  # id -> list of (t, mech, me)
    for o in obs:
        me = o["self"]
        for m in o.get("mechs") or []:
            if m.get("kind", "mech") == "mech":
                tr.setdefault(m["id"], []).append((o["t"], m, me))
    out = {"obs": len(obs), "span_s": obs[-1]["t"] - obs[0]["t"], "mechs": {}}
    for mid, rows in tr.items():
        d = {"first_seen_t": rows[0][0], "last_seen_t": rows[-1][0], "n_obs": len(rows)}
        d["weapons"] = sorted({w for _, m, _ in rows for w in m.get("weapons") or []})
        d["cubes_max"] = max(m.get("cubes", 0) for _, m, _ in rows)
        d["hp_first_last"] = (rows[0][1].get("hp"), rows[-1][1].get("hp"))
        sp = [math.hypot(m["vel"][0], m["vel"][1]) for _, m, _ in rows if m.get("vel")]
        d["speed_p50_p90_max"] = (round(pct(sp, .5), 1), round(pct(sp, .9), 1), round(max(sp), 1))
        d["frac_speed_gt_walk+1"] = round(sum(s > walk + 1 for s in sp) / max(len(sp), 1), 2)  # boosting
        d["frac_speed_lt_5_silent"] = round(sum(s < 5 for s in sp) / max(len(sp), 1), 2)
        rng, rad, tang, aimerr, lead, still_err = [], [], [], [], [], []
        for _, m, me in rows:
            dx, dy = me["pos"][0] - m["pos"][0], me["pos"][1] - m["pos"][1]
            r = math.hypot(dx, dy)
            rng.append(r)
            if m.get("vel") and r > 1:
                ux, uy = dx / r, dy / r
                rad.append(m["vel"][0] * ux + m["vel"][1] * uy)
                tang.append(abs(-m["vel"][0] * uy + m["vel"][1] * ux))
            if m.get("aim"):
                e = abs(wrap(math.atan2(dy, dx) - m["aim"][0]))
                aimerr.append(e)
                if math.hypot(me["vel"][0], me["vel"][1]) < 1.5:
                    still_err.append(e)
        d["range_p10_p50_p90"] = tuple(round(pct(rng, q), 0) for q in (.1, .5, .9))
        d["radial_speed_p50"] = round(pct(rad, .5), 1)           # <0 = closing
        d["tangential_speed_p50"] = round(pct(tang, .5), 1)       # strafing
        d["aim_err_deg_p50_p90"] = (round(math.degrees(pct(aimerr, .5)), 1), round(math.degrees(pct(aimerr, .9)), 1))
        d["aim_err_deg_when_we_still_p50"] = round(math.degrees(pct(still_err, .5)), 1) if still_err else None
        d["frac_aim_within_5deg"] = round(sum(e < math.radians(5) for e in aimerr) / max(len(aimerr), 1), 2)
        # cover: our LOS to them unknown here; use fraction of obs where they were visible while far
        d["charging_frac"] = round(sum(bool(m.get("charging")) for _, m, _ in rows) / len(rows), 2)
        # direction changes of velocity (strafe period)
        flips, last = 0, 0
        for _, m, me in rows:
            dx, dy = me["pos"][0] - m["pos"][0], me["pos"][1] - m["pos"][1]
            r = math.hypot(dx, dy) or 1
            s = (-m["vel"][0] * dy / r + m["vel"][1] * dx / r) if m.get("vel") else 0
            sg = 1 if s > 2 else -1 if s < -2 else 0
            if sg and last and sg != last:
                flips += 1
            if sg:
                last = sg
        d["strafe_flips"] = flips
        out["mechs"][mid] = d
    # own damage
    dmg = [(o["t"], e, o["self"]) for o in obs for e in o.get("events") or [] if e.get("type") == "damaged"]
    hits = [(o["t"], e) for o in obs for e in o.get("events") or [] if e.get("type") == "hit"]
    byw = collections.Counter()
    cnt = collections.Counter()
    rear = 0.0
    rng_hit = collections.defaultdict(list)
    for t, e, me in dmg:
        byw[(e.get("by"), e.get("weapon"))] += e["amount"]
        cnt[(e.get("by"), e.get("weapon"))] += 1
        if e.get("rear"):
            rear += e["amount"]
        src = next((m for _, m, _ in tr.get(e.get("by"), []) if False), None)
    tot = sum(byw.values())
    out["damage_taken"] = {"total": tot, "by_source_weapon": {f"{k[0]}:{k[1]}": (round(v), cnt[k]) for k, v in byw.items()},
                           "rear_fraction": round(rear / tot, 2) if tot else 0.0}
    # range at damage time (nearest recorded sighting of the shooter)
    rr = collections.defaultdict(list)
    for o in obs:
        for e in o.get("events") or []:
            if e.get("type") == "damaged" and e.get("by") is not None:
                for m in o.get("mechs") or []:
                    if m["id"] == e["by"]:
                        rr[e["weapon"]].append(math.hypot(o["self"]["pos"][0] - m["pos"][0], o["self"]["pos"][1] - m["pos"][1]))
                        break
    out["damage_range_by_weapon_p50"] = {k: (round(pct(v, .5)), len(v)) for k, v in rr.items()}
    out["our_hits_dealt"] = {"n": len(hits), "total": sum(e["amount"] for _, e in hits),
                             "rear_hits": sum(bool(e.get("rear")) for _, e in hits)}
    hp = [(o["t"], o["self"]["hp"]) for o in obs]
    out["our_hp_start_end"] = (hp[0][1], hp[-1][1])
    # fire-rate evidence
    shots = collections.defaultdict(list)
    for o in obs:
        for s in o.get("sounds") or []:
            shots[s["kind"]].append(o["t"])
    out["sound_counts"] = {k: len(v) for k, v in shots.items()}
    lt = sorted({round(o["t"], 1) for o in obs for e in o.get("events") or [] if e.get("weapon") == "laser" and e.get("type") == "damaged"})
    out["laser_hit_times"] = lt
    gt = sorted({o["t"] for o in obs for e in o.get("events") or [] if e.get("weapon") == "gun" and e.get("type") == "damaged"})
    out["gun_hit_gaps_s_p50"] = round(pct([b - a for a, b in zip(gt, gt[1:])], .5), 2) if len(gt) > 1 else None
    # our own movement
    sp = [math.hypot(o["self"]["vel"][0], o["self"]["vel"][1]) for o in obs]
    out["our_speed_p50_p90"] = (round(pct(sp, .5), 1), round(pct(sp, .9), 1))
    out["our_boost_frac_sound"] = round(sum(s > walk + 1 for s in sp) / len(sp), 2)
    out["zone_dps_first"] = obs[0]["zone"].get("dps")
    out["deaths_heard"] = sum(1 for o in obs for s in o.get("sounds") or [] if s["kind"] == "death")
    return out


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "check", "stream.jsonl.gz")
    hello, obs = load(path)
    print(json.dumps(analyse(hello, obs), indent=1, default=str))


if __name__ == "__main__":
    main()
