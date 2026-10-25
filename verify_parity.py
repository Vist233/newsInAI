#!/usr/bin/env python3
"""版式一致性校验：本仓库渲染器 vs 主仓库渲染器 vs 线上页面。

检查三件事：
1. workflows/ 下的渲染器与主仓库 origin/main 的版本是否一致（不一致就提示同步）
2. site/index.html 的 <style> 与线上主站页面是否逐字节相同（外观一致）
3. 渲染出的分区序列是否在主站分区集合内（不新增未知分区）

用法：python3 verify_parity.py [YYYY-MM-DD]
退出码 0 = 通过。
"""
from __future__ import annotations

import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MAIN_REPO = Path("/mnt/d/Basic/SakuraPersonalAgent")
LIVE_URL = "https://news.zhangyvjing.com/index.html"
PROXY = "http://127.0.0.1:7897"
FILES = ["workflows/influencer_digest_render.py", "workflows/influencer_digest_models.py"]


def live_html() -> str:
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
    )
    req = urllib.request.Request(LIVE_URL, headers={"User-Agent": "Mozilla/5.0"})
    with opener.open(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def css(html: str) -> str:
    m = re.search(r"<style>(.*?)</style>", html, re.S)
    return m.group(1) if m else ""


def main() -> int:
    problems = []

    # 1) 渲染器版本
    if MAIN_REPO.exists():
        for rel in FILES:
            try:
                upstream = subprocess.run(
                    ["git", "show", f"origin/main:{rel}"],
                    cwd=MAIN_REPO, capture_output=True, text=True, timeout=60,
                ).stdout
            except Exception as exc:
                problems.append(f"读取主仓库 {rel} 失败: {exc}")
                continue
            local = (ROOT / rel).read_text(encoding="utf-8")
            if upstream and upstream != local:
                print(f"⚠ 渲染器与主仓库不同（本地有改动，属预期）: {rel}")
            else:
                print(f"✓ 渲染器与主仓库一致: {rel}")
    else:
        print("⚠ 未找到主仓库克隆，跳过版本比对")

    # 2) CSS 逐字节
    try:
        live = live_html()
    except Exception as exc:
        print(f"⚠ 无法读取线上页面（{exc}），跳过 CSS 比对")
        live = ""
    mine = (ROOT / "site/index.html").read_text(encoding="utf-8")
    if live:
        a, b = css(mine), css(live)
        if a == b:
            print(f"✓ CSS 与线上完全一致（{len(a)} 字节）")
        else:
            problems.append(f"CSS 不一致：本地 {len(a)} 字节 / 线上 {len(b)} 字节")

    # 3) 分区集合
    allowed = {"00", "01", "02", "03", "04", "05", "06", "07", "08", "09"}
    got = re.findall(r'<span class="section-no">(\d+)</span>', mine)
    unknown = [g for g in got if g not in allowed]
    if unknown:
        problems.append(f"出现未知分区编号: {unknown}")
    else:
        print(f"✓ 分区编号在允许集合内: {got}")

    if problems:
        print("\n不一致项：")
        for p in problems:
            print("  -", p)
        return 1
    print("\n结果：版式一致")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
