"""A deliberately crude *approximation*, not the authoritative Mech Royale server.

It models enough kinematics, prism walls, zone damage, gun ray hits, and rear armour
to compare survival-biased policies against simple opponents.  Never treat its score as
a real-match prediction.
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .common import ROOT, load_bot_class, recorded_hello, report


def _inside(x: float, y: float, ring: list[float]) -> bool:
    hit = False
    for i in range(0, len(ring), 2):
        j = (i + 2) % len(ring)
        xi, yi, xj, yj = ring[i], ring[i + 1], ring[j], ring[j + 1]
        if (yi > y) != (yj > y) and x < (xj-xi)*(y-yi)/(yj-yi) + xi: hit = not hit
    return hit


@dataclass
class World:
    config: dict[str, Any]
    prisms: list[dict[str, Any]]
    bounds: dict[str, float]
    cells: dict[tuple[int, int], list[dict[str, Any]]]

    @classmethod
    def load(cls, hello: dict[str, Any]) -> "World":
        data = json.loads((ROOT / "arena/v2/world.json").read_text())
        prisms = data.get("prisms", [])
        # Coarse spatial grid: it is fast, and deliberately less exact than server collision.
        cells: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for prism in prisms:
            ring = prism.get("ring", [])
            if not ring: continue
            xs, ys = ring[::2], ring[1::2]
            for gx in range(math.floor(min(xs)/16), math.floor(max(xs)/16)+1):
                for gy in range(math.floor(min(ys)/16), math.floor(max(ys)/16)+1):
                    cells.setdefault((gx, gy), []).append(prism)
        return cls(hello["config"], prisms, data["bounds"], cells)

    def blocked(self, x: float, y: float, z: float = 0) -> bool:
        for prism in self.cells.get((math.floor(x/16), math.floor(y/16)), []):
            if prism["base"] <= z + self.config["mech"]["height"] and z <= prism["top"] and _inside(x, y, prism["ring"]):
                if not any(_inside(x, y, hole) for hole in prism.get("holes", [])): return True
        return False

    def ray_clear(self, a: list[float], b: list[float]) -> bool:
        # Fixed samples are intentionally conservative and not server collision geometry.
        distance = math.dist(a[:2], b[:2]); samples = max(1, int(distance / 8))
        for n in range(1, samples):
            q = n / samples; x = a[0] + q*(b[0]-a[0]); y = a[1] + q*(b[1]-a[1]); z = a[2] + q*(b[2]-a[2])
            if self.blocked(x, y, z): return False
        return True


@dataclass
class Mech:
    ident: int; pos: list[float]; hp: float; max_hp: float; aim: float = 0.; vel: list[float] = field(default_factory=lambda:[0.,0.])
    alive: bool = True; cooldown: float = 0.; ammo: int = 12; reload: float = 0.


def _baseline(obs: dict[str, Any]) -> dict[str, Any]:
    me, enemies = obs["self"], obs["mechs"]
    x, y = me["pos"][:2]; target = min(enemies, key=lambda e: math.dist(e["pos"][:2], [x,y]), default=None)
    if target:
        yaw = math.atan2(target["pos"][1]-y, target["pos"][0]-x)
        return {"tick":obs["tick"], "move":[-math.cos(yaw),-math.sin(yaw)], "aim":[yaw,0], "fire":[True,False], "boost":True}
    return {"tick":obs["tick"], "move":[0,0], "aim":[0,0], "fire":[False,False]}


def _zone(config: dict[str, Any], t: float) -> tuple[list[float], float, float]:
    center, radius = list(config["zone"]["start_center"]), float(config["zone"]["start_radius"])
    for phase in config["zone"]["phases"]:
        hold, shrink = phase["hold_s"], phase["shrink_s"]
        if t <= hold: return center, radius, phase["dps"]
        t -= hold
        if t < shrink:
            # The real next center is random; hold current center in this approximation.
            return center, radius + (phase["radius"]-radius)*t/shrink, phase["dps"]
        radius = phase["radius"]; t -= shrink
    return center, radius, config["zone"]["phases"][-1]["dps"]


def run(policy_factory: Callable[[dict[str, Any]], Any] | None = None, matches: int = 1, seed: int = 1,
        max_seconds: float | None = None) -> dict[str, Any]:
    hello = recorded_hello(); config = hello["config"]; world = World.load(hello)
    cls = load_bot_class() if policy_factory is None else None
    rng = random.Random(seed); placements: list[int] = []
    for game in range(matches):
        policy = (policy_factory or cls)(hello)
        mechs = []
        margin = config["match"]["arena_margin"]
        min_x, min_y = world.bounds["minX"], world.bounds["minY"]
        max_x, max_y = world.bounds["maxX"], world.bounds["maxY"]
        for ident in range(int(config["match"]["mechs"])):
            for _ in range(1000):
                p = [rng.uniform(min_x+margin,max_x-margin), rng.uniform(min_y+margin,max_y-margin), 0.]
                if not world.blocked(*p): break
            mechs.append(Mech(ident,p,float(config["mech"]["hp"]),float(config["mech"]["hp"])))
        time_s, tick, dead_order = 0., 0, []
        limit = min(float(config["match"]["duration_s"]), max_seconds) if max_seconds is not None else float(config["match"]["duration_s"])
        while time_s < limit and sum(m.alive for m in mechs) > 1:
            alive = [m for m in mechs if m.alive]; center, radius, dps = _zone(config, time_s)
            actions = []
            for m in alive:
                enemies = [{"id":e.ident,"kind":"mech","pos":e.pos,"vel":e.vel+[0.],"aim":[e.aim,0],"hp":e.hp,"max_hp":e.max_hp,"cubes":0,"weapons":["gun"]} for e in alive if e is not m]
                obs = {"type":"obs","tick":tick,"t":time_s,"alive":len(alive),"self":{"id":m.ident,"pos":m.pos,"vel":m.vel+[0.],"aim":[m.aim,0],"hp":m.hp,"max_hp":m.max_hp,"energy":100,"max_energy":100,"grounded":True,"cubes":0,"upgrades":[],"in_zone":True,"weapons":[{"kind":"gun","cooldown":m.cooldown,"ammo":m.ammo,"reload":m.reload,"stats":config["weapons"]["gun"]},None],"stats":config["mech"]},"mechs":enemies,"projectiles":[],"crates":[],"cubes":[],"pickups":[],"sounds":[],"beams":[],"events":[],"drops":[],"offer":None,"zone":{"center":center,"radius":radius,"next_center":center,"next_radius":radius,"shrink_start":time_s,"shrink_end":time_s,"dps":dps}}
                try: action = policy.act(obs) if m.ident == hello["slot"] else _baseline(obs)
                except Exception: action = {"move":[0,0],"fire":[False,False]}
                actions.append((m, action))
            for m, action in actions:
                move = action.get("move", [0,0]); length = math.hypot(float(move[0]), float(move[1])) or 1
                speed = config["mech"]["boost_speed"] if action.get("boost") else config["mech"]["walk_speed"]
                nx, ny = m.pos[0]+float(move[0])/length*speed*.1, m.pos[1]+float(move[1])/length*speed*.1
                if not world.blocked(nx,ny,m.pos[2]): m.vel=[nx-m.pos[0],ny-m.pos[1]]; m.pos[:2]=[nx,ny]
                aim = action.get("aim", [m.aim,0]); m.aim = float(aim[0])
                m.cooldown = max(0.,m.cooldown-.1); m.reload=max(0.,m.reload-.1)
                if m.reload == 0 and m.ammo == 0: m.ammo=int(config["weapons"]["gun"]["mag"])
                if action.get("fire", [False,False])[0] and m.cooldown == 0 and m.ammo:
                    targets = [e for e in mechs if e.alive and e is not m and math.dist(m.pos[:2],e.pos[:2]) <= config["weapons"]["gun"]["range"] and world.ray_clear(m.pos,e.pos)]
                    if targets:
                        target=min(targets,key=lambda e:math.dist(m.pos[:2],e.pos[:2])); bearing=math.atan2(m.pos[1]-target.pos[1],m.pos[0]-target.pos[0]); rear=abs((bearing-target.aim+math.pi)%(2*math.pi)-math.pi)>math.pi/2
                        target.hp -= config["weapons"]["gun"]["damage"]*(config["mech"]["rear_mult"] if rear else 1)
                    m.ammo-=1; m.cooldown=config["weapons"]["gun"]["cooldown"]
                    if not m.ammo: m.reload=config["weapons"]["gun"]["reload"]
            for m in alive:
                if math.dist(m.pos[:2],center) > radius: m.hp -= dps*.1
                if m.hp <= 0 and m.alive: m.alive=False; dead_order.append(m.ident)
            time_s += .1; tick += 2
        survivors=sorted((m for m in mechs if m.alive),key=lambda m:m.hp,reverse=True); ordered=dead_order+ [m.ident for m in survivors]
        placements.append(len(ordered)-ordered.index(hello["slot"]))
    return {"approximation": True,"matches":matches,"placements":placements,"mean_place":sum(placements)/len(placements),"win_rate":sum(p==1 for p in placements)/len(placements)}


if __name__ == "__main__": report(run())
