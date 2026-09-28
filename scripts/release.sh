#!/usr/bin/env bash
# Usage: scripts/release.sh stable patch|minor|major|X.Y.Z | scripts/release.sh beta [X.Y.Z]
set -euo pipefail
CHAN=${1:-}; ARG=${2:-}
STABLE_RE='^v[0-9]+\.[0-9]+\.[0-9]+$'; BETA_RE='^v[0-9]+\.[0-9]+\.[0-9]+-beta\.[0-9]+$'
latest() { git tag --list "$1" | sort -V | tail -1; }
next_stable() {
  local cur=${1#v} part=$2
  IFS=. read -r M m p <<<"$cur"
  case "$part" in major) echo "v$((M+1)).0.0";; minor) echo "v$M.$((m+1)).0";; patch) echo "v$M.$m.$((p+1))";; esac
}
if [ "$CHAN" = stable ]; then
  case "$ARG" in patch|minor|major) TAG=$(next_stable "$(latest 'v[0-9]*' | grep -v beta || echo v0.0.0)" "$ARG");; *) TAG="v$ARG";; esac
  echo "$TAG" | grep -Eq "$STABLE_RE" || { echo "bad stable tag: $TAG"; exit 1; }
elif [ "$CHAN" = beta ]; then
  if [ -n "$ARG" ]; then BASE="v$ARG"; BASE=${BASE%-beta*}; else BASE=$(latest 'v[0-9]*' | grep -v beta || echo v0.1.0); fi
  N=1; while git rev-parse "$BASE-beta.$N" >/dev/null 2>&1; do N=$((N+1)); done
  TAG="$BASE-beta.$N"
  echo "$TAG" | grep -Eq "$BETA_RE" || { echo "bad beta tag: $TAG"; exit 1; }
else echo "usage: $0 stable patch|minor|major|X.Y.Z | $0 beta [X.Y.Z]"; exit 1; fi
git rev-parse "$TAG" >/dev/null 2>&1 && { echo "tag exists: $TAG"; exit 1; }
python3 -m pytest tests/ -q
esphome config heatwhisper_esp32.yaml
esphome config heatwhisper_esp32_s3_rs485.yaml
esphome config heatwhisper_pico_w.yaml
git tag "$TAG" && git push origin "$TAG"
echo "released $TAG"
