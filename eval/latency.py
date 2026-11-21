"""Measure recorded-observation response latency in-process and through bot.py."""
from __future__ import annotations

import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from .common import ROOT, load_bot_class, report, stream


def _stats(samples: list[float]) -> dict[str, float]:
    assert samples, "no observations recorded"
    ordered = sorted(samples)
    def percentile(p: float) -> float:
        return ordered[min(len(ordered)-1, max(0, round((len(ordered)-1)*p)))]
    return {"count":len(samples),"median_ms":statistics.median(samples),"p95_ms":percentile(.95),"p99_ms":percentile(.99),"max_ms":max(samples)}


def in_process(bot_path: Path | None = None) -> dict[str, float]:
    messages=stream(); hello=next(m for m in messages if m.get("type")=="hello")
    bot=load_bot_class(bot_path)(hello); timings=[]
    for obs in (m for m in messages if m.get("type")=="obs"):
        start=time.perf_counter_ns(); action=bot.act(obs); elapsed=(time.perf_counter_ns()-start)/1e6
        assert isinstance(action,dict) and action.get("tick")==obs["tick"]
        timings.append(elapsed)
    return _stats(timings)


def subprocess_run(bot_path: Path | None = None) -> dict[str, float]:
    bot_path=bot_path or ROOT/"bot.py"; messages=stream(); observations=[m for m in messages if m.get("type")=="obs"]
    process=subprocess.Popen([sys.executable,"-u",str(bot_path)],cwd=ROOT,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
    assert process.stdin and process.stdout
    timings=[]
    try:
        hello=next(m for m in messages if m.get("type")=="hello")
        process.stdin.write(json.dumps(hello)+"\n"); process.stdin.flush(); ready=json.loads(process.stdout.readline()); assert ready.get("type")=="ready"
        for obs in observations:
            start=time.perf_counter_ns(); process.stdin.write(json.dumps(obs)+"\n"); process.stdin.flush(); action=json.loads(process.stdout.readline()); elapsed=(time.perf_counter_ns()-start)/1e6
            assert action.get("tick")==obs["tick"], "stale subprocess action"; timings.append(elapsed)
        process.stdin.write(json.dumps({"type":"end","place":1,"kills":0})+"\n"); process.stdin.close(); process.wait(timeout=5)
    finally:
        if process.poll() is None: process.kill()
    return _stats(timings)


def run(bot_path: Path | None = None) -> dict[str, Any]:
    return {"in_process":in_process(bot_path),"subprocess":subprocess_run(bot_path),"budget_ms":50,"target_p99_ms":15}


if __name__ == "__main__": report(run())
