#!/usr/bin/env python3
"""只重算 insight 并重新建站推送（不动采集，不重跑摘要）。

用法：python3 regen_insight.py [YYYY-MM-DD]
规则：
  今天：4-6 句硬事实，每句主体 + 动作 + 数字，禁止套话
  转向：2 句，第一句点名一个过去具体事件做对照；无法确定就只给方向，不许编
  对你：1 句可执行动作，落到具体文件/命令/指标
任一段不合格就重试该段最多 3 次；「今天」始终不合格 → 整段 Insight 不渲染（宁缺勿滥）。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import daily_run as D  # noqa: E402

BANNED = ("值得关注", "值得注意", "反映出", "背后", "整体来看", "共同主线", "这说明", "标志着",
          "本质上", "进一步", "同时", "此外", "不难看出", "总而言之", "由此可见", "值得注意的是",
          "获得", "条评论", "Hacker News 帖子", "分和", "热度")

READER = ("读者是 Zhang：他在做 Agent harness（Sakura Code / Pi）和 Terminal-Bench 评测，"
          "关心工具调用、上下文缓存、评测口径、故障恢复。")


def facts_lines(items: list[dict], n: int = 22) -> str:
    out = []
    for i in items[:n]:
        t = i.get("title") or ""
        s = (i.get("summary") or "").replace("\n", " ")
        out.append(f"- {t}" + (f"｜{s[:160]}" if s else ""))
    return "\n".join(out)


def gen(part: str, items: list[dict], key: str) -> str:
    body = facts_lines(items)
    if part == "今天":
        rule = ("写 4 到 5 句，每句一个具体事实：谁做了什么/发布了什么/改了什么 + 关键数字"
                "（金额、比例、版本号、时长、容量、条数、代码行数等）。"
                "数字必须是这件事本身的量，不许写 HN 分数、评论条数、star 数这种热度指标。"
                "不许连续两句用同一种句式。只输出这些句子，不要标签、不要开场白、不要评价词。")
        lo, hi = 60, 400
    elif part == "转向":
        rule = ("写 2 句。第一句必须点名一个具体事件做对照（可以是三个月前的公开事件，也可以是条目里"
                "出现的旧版本/旧做法），说清哪一类行为变了；第二句给方向（变多/变少/从 A 转 B）。"
                "如果无法确定任何可对照的具体事件，就只写第二句，不要编造。只输出这两句。")
        lo, hi = 25, 200
    else:
        rule = ("写 1 句可执行动作，必须和读者自己的工作直接相关（Agent harness、工具调用、评测、"
                "上下文/缓存、故障恢复），落到具体对象：哪个仓库、哪个文件、哪个指标、跑哪条命令。"
                "不许写『要重视』『需关注』『加强』『持续观察』这类空话，也不许随便挑一条新闻里的仓库。"
                "只输出这一句。")
        lo, hi = 15, 120

    prompt = (f"{READER}\n你是给他写内部判断的技术编辑。读下面今天的条目，只写「{part}」这一部分。\n"
              f"{rule}\n"
              f"禁止出现的词：{'、'.join(BANNED)}。\n"
              f"只允许使用条目里出现的事实，不许补充外部常识。\n\n{body}")
    for attempt in range(3):
        try:
            txt = D.clean(D.ask(prompt, key, 2000))
        except Exception as e:
            D.log(f"insight {part} 第{attempt+1}次失败 {type(e).__name__}")
            continue
        txt = re.sub(r"^(今天|转向|对你)\s*[：:]\s*", "", txt).strip()
        hits = [w for w in BANNED if w in txt]
        if hits:
            D.log(f"insight {part} 含套话 {hits}，重试")
            continue
        if not (lo <= len(txt) <= hi):
            D.log(f"insight {part} 长度 {len(txt)} 不在 {lo}-{hi}，重试")
            continue
        if part == "今天" and len(re.findall(r"\d", txt)) < 4:
            D.log("insight 今天 数字太少，重试")
            continue
        return txt
    return ""


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    p = D.ROOT / "content" / f"{day}.json"
    payload = json.loads(p.read_text(encoding="utf-8"))
    items = payload.get("items") or []
    key = D.api_key()

    parts = {}
    for name in ("今天", "转向", "对你"):
        v = gen(name, items, key)
        D.log(f"insight {name}: {len(v)} 字")
        if v:
            parts[name] = v

    if "今天" not in parts:
        payload["summary"] = ""
        D.log("「今天」生成失败 → Insight 整段不渲染")
    else:
        payload["summary"] = "\n".join(f"{k}：{parts[k]}" for k in ("今天", "转向", "对你") if k in parts)
        print(payload["summary"])

    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    r = subprocess.run([sys.executable, "build.py", day], cwd=D.ROOT, capture_output=True, text=True)
    D.log(f"build rc={r.returncode} {(r.stdout or '').strip().splitlines()[-1] if r.stdout else ''}")
    if r.returncode != 0:
        D.log((r.stderr or "")[-400:])
        return 1

    subprocess.run(["bash", "-c", "rm -rf daily && mkdir -p daily && cp -r site/. daily/"], cwd=D.ROOT, check=True)
    D.git("add", "-A", "content", "daily")
    rc, out = D.git("commit", "-m", f"insight: {day} 重算")
    D.log(f"commit rc={rc} {out.splitlines()[0] if out else ''}")
    rc, out = D.git("push", "origin", "main")
    D.log(f"push main rc={rc} {out.splitlines()[-1] if out else ''}")
    if rc != 0:
        return 1

    wt = Path("/tmp/newsinai-gh2")
    subprocess.run(["bash", "-c", f"rm -rf {wt} && git worktree prune && git worktree add --detach {wt} >/dev/null 2>&1"],
                   cwd=D.ROOT)
    if wt.exists():
        subprocess.run(["bash", "-c", "git checkout gh-pages >/dev/null 2>&1 && rm -rf daily && mkdir -p daily && "
                                     f"cp -r {D.ROOT}/site/. daily/ && touch .nojekyll"], cwd=wt)
        subprocess.run(["git", "add", "-A"], cwd=wt)
        subprocess.run(["git", "-c", "user.name=Vist233", "-c", "user.email=Vist233@users.noreply.github.com",
                        "commit", "-m", f"publish: {day} insight"], cwd=wt, capture_output=True)
        r2 = subprocess.run(["git", "push", "origin", "gh-pages"], cwd=wt, capture_output=True, text=True)
        D.log(f"push gh-pages rc={r2.returncode} {(r2.stdout + r2.stderr).strip().splitlines()[-1] if (r2.stdout or r2.stderr) else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
