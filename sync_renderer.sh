#!/usr/bin/env bash
# 从主仓库同步渲染器（保证版式跟随主站变化）。
# 用法: ./sync_renderer.sh [主仓库路径]
set -euo pipefail
MAIN="${1:-/mnt/d/Basic/SakuraPersonalAgent}"
cd "$(dirname "$0")"

if [ ! -d "$MAIN/.git" ]; then
  echo "找不到主仓库: $MAIN" >&2
  exit 1
fi

git -C "$MAIN" fetch --depth=1 origin main >/dev/null 2>&1 || true
for f in workflows/influencer_digest_render.py workflows/influencer_digest_models.py; do
  git -C "$MAIN" show "origin/main:$f" > "$f"
  echo "synced $f"
done
echo "注意：渲染器每次同步后要重跑 build.py，并确认 02 Worth Reading 分区补丁仍在。"
grep -q '"news", "02"' workflows/influencer_digest_render.py \
  && echo "✓ 02 分区补丁仍在" \
  || echo "⚠ 02 分区补丁被覆盖，需要重新加"
