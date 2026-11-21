"""Adversarial observation checks for a Policy/Bot action surface (stdlib only)."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Callable

from .common import ROOT, load_bot_class, recorded_hello


class SchemaError(AssertionError):
    pass


def _resolve(schema: dict[str, Any], root: dict[str, Any]) -> dict[str, Any]:
    while "$ref" in schema:
        ref = schema["$ref"]
        if not ref.startswith("#/"):
            raise SchemaError(f"external ref unsupported: {ref}")
        item: Any = root
        for key in ref[2:].split("/"):
            item = item[key]
        schema = item
    return schema


def validate(value: Any, schema: dict[str, Any], root: dict[str, Any], where: str = "$") -> None:
    """Deliberately small draft-07 subset used by this repository's action schema."""
    schema = _resolve(schema, root)
    for branch_name in ("oneOf", "anyOf"):
        if branch_name in schema:
            errors = []
            for branch in schema[branch_name]:
                try:
                    validate(value, branch, root, where)
                    return
                except SchemaError as exc:
                    errors.append(str(exc))
            raise SchemaError(f"{where}: no {branch_name} branch matched ({errors[0]})")
    if "const" in schema and value != schema["const"]:
        raise SchemaError(f"{where}: expected {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        raise SchemaError(f"{where}: value not in enum")
    kind = schema.get("type")
    if kind == "object":
        if not isinstance(value, dict): raise SchemaError(f"{where}: expected object")
        for name in schema.get("required", []):
            if name not in value: raise SchemaError(f"{where}: missing {name}")
        for name, child in schema.get("properties", {}).items():
            if name in value: validate(value[name], child, root, f"{where}.{name}")
    elif kind == "array":
        if not isinstance(value, list): raise SchemaError(f"{where}: expected array")
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get("maxItems", float("inf")):
            raise SchemaError(f"{where}: wrong array length")
        if "items" in schema:
            for index, item in enumerate(value): validate(item, schema["items"], root, f"{where}[{index}]")
    elif kind == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
        raise SchemaError(f"{where}: expected number")
    elif kind == "string" and not isinstance(value, str): raise SchemaError(f"{where}: expected string")
    elif kind == "boolean" and not isinstance(value, bool): raise SchemaError(f"{where}: expected boolean")


def edge_observations() -> list[dict[str, Any]]:
    hello = recorded_hello()
    base = next(m for m in __import__("eval.common", fromlist=["stream"]).stream() if m.get("type") == "obs")
    cases = []
    empty = copy.deepcopy(base); empty.update(mechs=[], projectiles=[], crates=[], cubes=[], pickups=[], sounds=[], beams=[], events=[], drops=[], offer=None); cases.append(empty)
    offered = copy.deepcopy(empty); offered["tick"] = 2; offered["offer"] = {"id": 1, "expires": 0, "choices": [{"id": "armor"}, {"id": "plating"}, {"id": "sensors"}]}; cases.append(offered)
    nulls = copy.deepcopy(empty); nulls["tick"] = 4; nulls["events"] = [{"type":"damaged", "amount": 1, "weapon":"zone", "bearing":None, "by":None}]; nulls["drops"] = [{"id": 1, "pos":[0,0,0], "radius":8, "lands_in":0, "capture_s":4, "progress":0, "holder":None}]; cases.append(nulls)
    huge = copy.deepcopy(empty); huge["tick"] = 6; huge["mechs"] = [{"id": i + 20, "kind":"mech", "pos":[float(i), 0, 0], "vel":[0,0,0], "aim":[0,0], "hp":1, "max_hp":1, "cubes":0, "weapons":[]} for i in range(4096)]; cases.append(huge)
    zero_zone = copy.deepcopy(empty); zero_zone["tick"] = 8; zero_zone["zone"]["radius"] = 0; zero_zone["zone"]["next_radius"] = 0; cases.append(zero_zone)
    return cases


def run(policy_factory: Callable[[dict[str, Any]], Any] | None = None) -> dict[str, int]:
    """Feed hostile-but-schema-shaped observations and assert actions are valid."""
    hello = recorded_hello()
    if policy_factory is None:
        cls = load_bot_class(); policy_factory = cls
    policy = policy_factory(hello)
    root = json.loads((ROOT / "mechfight.schema.json").read_text())
    action_schema = root["definitions"]["Action"]
    cases = edge_observations()
    for obs in cases:
        action = policy.act(obs)
        assert isinstance(action, dict), "act must return a dict"
        assert action.get("tick") == obs["tick"], "action must echo tick"
        validate(action, action_schema, root)
    return {"cases": len(cases), "valid_actions": len(cases)}


if __name__ == "__main__":
    from .common import report
    report(run())
