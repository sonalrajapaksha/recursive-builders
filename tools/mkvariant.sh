#!/bin/bash
# usage: tools/mkvariant.sh NAME '{"LaserRange":150}'  -> branch tv-NAME off tune-base, docker-check, push, print hash
set -e
NAME=$1; JSON=$2
ROOT=$(git rev-parse --show-toplevel)
A=${ARENA:-/Users/sonalrajapaksha/Documents/buildathon/recursive-builders/arena}
W=/tmp/ext/tv-$NAME
git -C "$ROOT" worktree remove --force "$W" 2>/dev/null || true
git -C "$ROOT" branch -D tv-$NAME 2>/dev/null || true
git -C "$ROOT" worktree add -q -b tv-$NAME "$W" "${BASE:-tune-base}"
echo "$JSON" > "$W/mech/tune.json"
cd "$W"
docker build --platform linux/amd64 -q -t tv-$NAME . >/dev/null
OUT=$(python3 check/check.py --map-dir /arena -- docker run --rm -i --platform linux/amd64 --network none --cpus 1 --memory 512m --read-only --tmpfs /tmp:rw,size=64m --user 65534:65534 -v "$A:/arena:ro" tv-$NAME 2>&1 | tail -3)
echo "$OUT" | grep -q PASS || { echo "CHECK FAILED: $OUT"; exit 1; }
git add -A && git commit -qm "tune variant $NAME: $JSON"
git push -q origin tv-$NAME 2>/dev/null
echo "tv-$NAME $(git rev-parse HEAD) $JSON"
docker rmi -f tv-$NAME >/dev/null 2>&1 || true
