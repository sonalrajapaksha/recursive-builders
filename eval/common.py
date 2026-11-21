"""Small helpers shared by evaluation scripts; these tools are not a match server."""
from __future__ import annotations

import gzip
import importlib.util
import json
import math
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]


def stream(path: Path | None = None) -> list[dict[str, Any]]:
    """Read the supplied conformance recording without mutating it."""
    path = path or ROOT / "check" / "stream.jsonl.gz"
    with gzip.open(path, "rt", encoding="utf-8") as source:
        return [json.loads(line) for line in source if line.strip()]


def recorded_hello() -> dict[str, Any]:
    return next(message for message in stream() if message.get("type") == "hello")


def load_bot_class(path: Path | None = None) -> type:
    """Import a wrapper-style bot without allowing its mf.run() loop to start."""
    path = path or ROOT / "bot.py"
    import mechfight
    original = mechfight.run
    captured: dict[str, type] = {}

    def capture(cls: type) -> None:
        captured["class"] = cls

    mechfight.run = capture
    try:
        spec = importlib.util.spec_from_file_location("evaluated_bot", path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return captured.get("class", getattr(module, "Bot"))
    finally:
        mechfight.run = original


def finite(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def report(value: Any) -> None:
    """Evaluation CLIs report on stderr so bot protocol stdout remains clean."""
    print(json.dumps(value, sort_keys=True), file=sys.stderr)
