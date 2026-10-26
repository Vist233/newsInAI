#!/usr/bin/env python3
"""只重写「02 Worth Reading」的 4 条理由，然后重建 + 推送。不动其它内容。"""
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path("/mnt/d/Basic/newsInAI")
sys.path.insert(0, str(ROOT))
import daily_run as D  # noqa: E402

day = datetime.now().strftime("%Y-%m-%d")
cf = ROOT / "content" / f"{day}.json"
data = json.loads(cf.read_text(encoding="utf-8"))
raw = json.loads((ROOT / "raw" / f"{day}.json").read_text(encoding="utf-8"))
key = D.api_key()

# 从 raw 里按标题找回 points / stars_today
hn = {h["title"]: h for h in raw.get("hacker_news", [])}
gh = {g["repo"]: g for g in raw.get("github_trending", [])}
# 已写好的正文摘要：给模型提供事实依据，避免它只能复述标题
ctx = {i["title"]: i["summary"] for i in data["items"] if i["kind"] != "news" and i.get("summary")}

for item in data["items"]:
    if item["kind"] != "news":
        continue
    t = item["title"]
    if t in hn:
        h = hn[t]
        extra = (f"标题：{t}\n社区热度：Hacker News {h['points']} 票、{h['comments']} 条讨论\n"
                 f"内容介绍：{ctx.get(t, '')}")
    elif t in gh:
        g = gh[t]
        extra = (f"标题：{t}\n今日新增星标：{g.get('stars_today','0')} 个\n"
                 f"内容介绍：{ctx.get(t, g.get('desc',''))}")
    else:
        extra = f"标题：{t}"
    why = D.why_line(
        f"根据下面的内容介绍，用简体中文写一句 30-50 字，说明它为什么值得看："
        f"点出其中的具体结论、方法或事实，不要复述标题，不要解释挑选标准。"
        f"只能用给出的信息，不要编造数字，不要把星标数说成投票数。"
        f"禁止「值得单独看」「值得关注」「值得一看」「凸显」这类套话。"
        f"只输出这一句话。\n\n{extra[:700]}", key)
    print(f"· {t[:44]}\n  {why}")
    item["summary"] = why

cf.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

r = subprocess.run([sys.executable, "build.py", day], cwd=ROOT, capture_output=True, text=True)
print("\nbuild:", (r.stdout or r.stderr).strip().splitlines()[-1])
subprocess.run(["bash", "-c", "rm -rf daily && mkdir -p daily && cp -r site/. daily/"], cwd=ROOT, check=True)
D.git("add", "-A", "content", "daily")
D.git("commit", "-m", f"daily: {day} 精选理由改写")
print("push main:", D.git("push", "origin", "main")[1].splitlines()[-1])

wt = Path("/tmp/newsinai-gh2")
subprocess.run(["bash", "-c", f"rm -rf {wt} && git worktree add --detach {wt} >/dev/null 2>&1"], cwd=ROOT)
subprocess.run(["bash", "-c", "git checkout gh-pages >/dev/null 2>&1 && rm -rf daily && mkdir -p daily && "
                             f"cp -r {ROOT}/site/. daily/ && touch .nojekyll"], cwd=wt)
subprocess.run(["git", "add", "-A"], cwd=wt)
subprocess.run(["git", "-c", "user.name=Vist233", "-c", "user.email=Vist233@users.noreply.github.com",
                "commit", "-m", f"publish: {day} picks"], cwd=wt, capture_output=True)
r2 = subprocess.run(["git", "push", "origin", "gh-pages"], cwd=wt, capture_output=True, text=True)
print("push gh-pages:", (r2.stdout + r2.stderr).strip().splitlines()[-1])
subprocess.run(["bash", "-c", f"cd {ROOT} && git worktree remove {wt} --force"], capture_output=True)
