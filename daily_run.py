#!/usr/bin/env python3
"""newsInAI 每日流水线：采集 → 生成摘要/判断 → 建站 → 提交推送。

设计原则：
- 任何一步失败都不阻断发布（摘要缺失就留空，页面照出），失败写进日志并在推送信息里标注
- 摘要走本机模型网关（与主站同一套），但**不依赖**它：模型挂了就降级发布
- 推送 main（源码 + daily/ 成品）与 gh-pages（成品）两个分支
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

GATEWAY = os.environ.get("GATEWAY", "http://127.0.0.1:33427/v1")
MODEL = os.environ.get("MODEL", "workbuddy-ai/deepseek-v4.1-flash")
LOG = ROOT / "logs"
LOG.mkdir(exist_ok=True)


def log(msg: str) -> None:
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line, flush=True)
    with (LOG / f"{datetime.now():%Y-%m-%d}.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def api_key() -> str:
    cmd = subprocess.run(
        ["bash", "-c", "sed -n 's/^ *key_cmd: *//p' ~/.hermes/config.yaml | head -1"],
        capture_output=True, text=True).stdout.strip().strip('"').strip("'")
    return subprocess.run(["bash", "-c", cmd], capture_output=True, text=True).stdout.strip().splitlines()[0]


def ask(prompt: str, key: str, max_tokens: int = 400) -> str:
    body = json.dumps({"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                       "temperature": 0.3, "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(f"{GATEWAY}/chat/completions", data=body,
                                 headers={"Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    return data["choices"][0]["message"]["content"].strip()


CJK = re.compile(r"[\u4e00-\u9fff]")


def cjk_len(s: str) -> int:
    return len(CJK.findall(s))


BAN = ("提示词", "输入 json", "输出要求", "——")


def clean(text: str) -> str:
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text).strip()
    text = re.sub(r"\n?```$", "", text).strip()
    text = text.replace("**", "").replace("*", "").replace("`", "")
    text = re.sub(r"\s+", " ", text).strip(" -—:")
    return text


def trim_to(text: str, hi: int) -> str:
    """按句末标点截到 hi 字以内，避免整条被丢弃。"""
    if cjk_len(text) <= hi:
        return text
    out = ""
    for ch in text:
        if cjk_len(out + ch) > hi:
            break
        out += ch
    cut = max(out.rfind(p) for p in "。！？；")
    return (out[:cut + 1] if cut > hi * 0.5 else out).strip()


def summarize(kind: str, title: str, extra: str, key: str, lo: int = 60, hi: int = 220) -> str:
    """生成 60-220 汉字摘要；不合规重试，超长按句截断，彻底失败返回空串。"""
    hint = {"hn": "Hacker News 上的技术讨论",
            "gh": "GitHub 上的开源项目",
            "paper": "arXiv 论文"}[kind]
    draft = ""
    for attempt in range(2):
        try:
            if attempt == 0:
                prompt = (f"用简体中文写一段 {lo}-{hi} 字的摘要，介绍这个{hint}。"
                          f"只输出摘要正文，不要标题、不要列表、不要 markdown、不要任何解释。"
                          f"必须写满 {lo} 字以上。不要使用破折号。\n\n"
                          f"标题：{title}\n补充信息：{extra[:900]}")
            else:
                prompt = (f"下面这段摘要太长了，请压缩到 150 字以内，保留关键事实，"
                          f"只输出压缩后的正文：\n\n{draft}")
            out = clean(ask(prompt, key))
        except Exception as e:
            log(f"  摘要失败 {type(e).__name__}: {str(e)[:60]}")
            return ""
        n = cjk_len(out)
        if lo <= n <= hi and not any(b in out for b in BAN):
            return out
        if n > hi:
            draft = out
        log(f"  摘要不合规（{n} 字），重试")
    if draft:
        fixed = trim_to(draft, hi)
        if cjk_len(fixed) >= lo:
            log(f"  截断到 {cjk_len(fixed)} 字后采用")
            return fixed
    return ""


def why_line(prompt: str, key: str, lo: int = 25, hi: int = 55) -> str:
    """一句话理由：命中套话或长度不合就重试，最多 3 次。"""
    BAD = ("值得一看", "值得关注", "值得单独看", "值得单独拎", "凸显", "深入了解", "降低门槛", "值得一看")
    best = ""
    for _ in range(3):
        try:
            out = clean(ask(prompt, key, 140))
        except Exception:
            continue
        if not out:
            continue
        best = best or out
        if lo <= len(out) <= hi and not any(b in out for b in BAD):
            return out
    return best


def git(*args: str, cwd: Path = ROOT) -> tuple[int, str]:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return r.returncode, (r.stdout + r.stderr).strip()


def main() -> int:
    day = datetime.now().strftime("%Y-%m-%d")
    log(f"=== 开始 {day} ===")
    errors: list[str] = []

    # 1) 采集
    try:
        r = subprocess.run([sys.executable, "collect.py"], cwd=ROOT, capture_output=True,
                           text=True, timeout=600,
                           env={**os.environ, "https_proxy": "http://127.0.0.1:7897",
                                "http_proxy": "http://127.0.0.1:7897"})
        log(f"collect rc={r.returncode} {(r.stdout or '').strip().splitlines()[-1] if r.stdout else ''}")
        if r.returncode != 0:
            errors.append("collect 非零退出")
    except Exception as e:
        errors.append(f"collect 异常 {type(e).__name__}")
        log(f"collect 异常: {e}")

    raw_path = ROOT / "raw" / f"{day}.json"
    if not raw_path.exists():
        log("没有采集结果，终止")
        return 1
    raw = json.loads(raw_path.read_text(encoding="utf-8"))

    key = api_key()
    items: list[dict] = []

    # 2) Hacker News（取前 10）
    hn = raw.get("hacker_news") or []
    for h in hn[:10]:
        s = summarize("hn", h["title"], f"链接 {h['url']}，{h['points']} 分、{h['comments']} 条评论", key)
        if not s:
            errors.append("HN 摘要缺失")
        items.append({"kind": "hacker_news", "source_id": "hn", "source_name": "Hacker News",
                      "title": h["title"], "url": h["url"], "published": h["published"],
                      "summary": s, "categories": ["hn"], "priority": "normal"})
    log(f"HN {len(hn[:10])} 条，摘要成功 {sum(1 for i in items if i['kind']=='hacker_news' and i['summary'])}")

    # 3) GitHub Trending（前 10）
    gh = raw.get("github_trending") or []
    for g in gh[:10]:
        s = summarize("gh", g["repo"], f"语言 {g['language']}，今日新增 {g['stars_today']} 星，简介：{g['desc']}", key)
        if not s:
            errors.append("GH 摘要缺失")
        items.append({"kind": "github_trending", "source_id": "github", "source_name": "GitHub Trending",
                      "title": g["repo"], "url": g["url"], "published": day,
                      "summary": s, "categories": [g.get("language") or "repo"], "priority": "normal"})
    log(f"GH {len(gh[:10])} 条，摘要成功 {sum(1 for i in items if i['kind']=='github_trending' and i['summary'])}")

    # 4) 论文（前 8）
    papers = raw.get("papers") or []
    for p in papers[:8]:
        title = re.sub(r"^Title:\s*", "", p["title"])
        s = summarize("paper", title, p.get("abstract", ""), key)
        if not s:
            errors.append("论文摘要缺失")
        items.append({"kind": "paper", "source_id": "arxiv", "source_name": "arXiv",
                      "title": title, "url": p["url"], "published": day,
                      "summary": s, "categories": ["paper"], "priority": "normal"})
    log(f"论文 {len(papers[:8])} 篇，摘要成功 {sum(1 for i in items if i['kind']=='paper' and i['summary'])}")

    # 5) 视频（近 14 天，取 5）
    try:
        import collect as C
        chans = ["https://www.youtube.com/@aiDotEngineer/videos",
                 "https://www.youtube.com/@ycombinator/videos",
                 "https://www.youtube.com/@anthropic-ai/videos"]
        vids = C.youtube_channels(chans, per_channel=2, days=14)[:5]
    except Exception as e:
        vids = []
        errors.append("视频采集失败")
        log(f"视频失败 {type(e).__name__}")
    for v in vids:
        why = why_line(
            f"用简体中文写一句 25-45 字的具体理由，说明这个视频为什么值得看。"
            f"必须点出视频里一个具体的东西（讲者、公司、数字、方法或结论）。"
            f"禁止使用「值得一看」「值得关注」「值得单独看」「凸显」「深入了解」这类空话。"
            f"只输出这一句话。\n{v['title']}", key)
        items.append({"kind": "youtube", "source_id": "yt", "source_name": v["channel"],
                      "title": v["title"], "url": v["url"],
                      "published": f"{v['upload_date'][:4]}-{v['upload_date'][4:6]}-{v['upload_date'][6:]}",
                      "summary": why, "categories": ["video"], "priority": "normal",
                      "image_url": f"https://i.ytimg.com/vi/{v['url'].rsplit('=',1)[-1]}/hqdefault.jpg"})
    log(f"视频 {len(vids)} 条")

    # 6) 02 Worth Reading：从 HN 高分 + GH 高星里挑 4 条
    picks = sorted(hn[:6], key=lambda x: -x["points"])[:2] + sorted(
        gh[:6], key=lambda x: -int((x.get("stars_today") or "0").replace(",", "") or 0))[:2]
    # 已写好的正文摘要：给模型事实依据，否则它只能复述标题
    ctx = {i["title"]: i["summary"] for i in items if i.get("summary")}
    for p in picks:
        t = p.get("title") or p.get("repo")
        if p.get("points") is not None:
            extra = (f"标题：{t}\n社区热度：Hacker News {p['points']} 票、{p.get('comments', 0)} 条讨论\n"
                     f"内容介绍：{ctx.get(t, '')}")
        else:
            extra = (f"标题：{t}\n今日新增星标：{p.get('stars_today', '0')} 个\n"
                     f"内容介绍：{ctx.get(t, p.get('desc', ''))}")
        why = why_line(
            f"根据下面的内容介绍，用简体中文写一句 30-50 字，说明它为什么值得看："
            f"点出其中的具体结论、方法或事实，不要复述标题，不要解释挑选标准。"
            f"只能用给出的信息，不要编造数字，不要把星标数说成投票数。"
            f"禁止「值得单独看」「值得关注」「值得一看」「凸显」这类套话。"
            f"只输出这一句话。\n\n{extra[:700]}", key)
        items.append({"kind": "news", "source_id": "pick", "source_name": "我的挑选",
                      "title": t, "url": p["url"], "published": day, "summary": why,
                      "categories": ["pick"], "priority": "high"})
    log(f"精选 {len(picks)} 条")

    # 7) Insight
    heads = "；".join(i["title"] for i in items[:8])
    try:
        insight = clean(ask(
            "你是技术编辑。根据下面今天的条目，写一段 200-320 字的简体中文判断，"
            "要有观点、指出共同主线、说明什么被高估。只输出正文，不要标题、不要列表。\n\n"
            + "\n".join(f"- [{i['kind']}] {i['title']}" for i in items[:20]), key, 700))
    except Exception as e:
        insight = ""
        errors.append("Insight 失败")
        log(f"Insight 失败 {type(e).__name__}")
    if cjk_len(insight) < 120:
        insight = f"今天的输入集中在 {heads[:120]} 这几条上。判断留白比硬凑更诚实：模型侧今天没有给出可用的综合。"
        errors.append("Insight 降级")

    # 8) 生活输入：按日轮换，不调模型
    FILMS = [("Her", 2013, "Spike Jonze", "把抽象的 AI 讨论拉回真实关系与投射"),
             ("Zodiac", 2007, "David Fincher", "讲证据链与偏执式核验，适合信息过载时看"),
             ("Moneyball", 2011, "Bennett Miller", "旧评价体系失灵时，怎么用证据重新决定下注"),
             ("Ikiru", 1952, "黑泽明", "提醒时间该压在哪件事上"),
             ("First Man", 2018, "Damien Chazelle", "把注意力从持续输入里抽出来的校准")]
    BOOKS = [("A Philosophy of Software Design", "John Ousterhout", "Chapter 2: The Nature of Complexity",
              "把复杂度当成要管理的对象，而不是代码行数"),
             ("The Craft of Research", "Wayne C. Booth 等", "Making Good Arguments",
              "论点、理由、证据、反驳拆成可检查的结构"),
             ("Thinking in Systems", "Donella H. Meadows", "Chapter 1: The Basics",
              "先看反馈回路与延迟，再谈单变量优化"),
             ("The Effective Engineer", "Edmond Lau", "Focus on High-Leverage Activities",
              "讲杠杆与高产出习惯")]
    idx = datetime.now().toordinal()
    f = FILMS[idx % len(FILMS)]
    b = BOOKS[idx % len(BOOKS)]

    payload = {
        "date": day,
        "summary": insight,
        "movie": {"title": f[0], "year": f[1], "director": f[2], "reason": f[3], "tags": ["film"]},
        "book": {"title": b[0], "author": b[1], "chapter": b[2], "reason": b[3], "tags": ["book"]},
        "items": items,
    }
    (ROOT / "content").mkdir(exist_ok=True)
    (ROOT / "content" / f"{day}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    log(f"内容写入 content/{day}.json，共 {len(items)} 条")

    # 9) 建站
    r = subprocess.run([sys.executable, "build.py", day], cwd=ROOT, capture_output=True, text=True)
    log(f"build rc={r.returncode} {(r.stdout or '').strip().splitlines()[-1] if r.stdout else ''}")
    if r.returncode != 0:
        log((r.stderr or "")[-500:])
        return 1

    # 10) 同步成品到 daily/ 并推送
    subprocess.run(["bash", "-c", "rm -rf daily && mkdir -p daily && cp -r site/. daily/"],
                   cwd=ROOT, check=True)
    tag = f"{day} 自动更新" + (f"（{len(errors)} 处降级）" if errors else "")
    git("add", "-A", "content", "raw", "daily", "logs")
    rc, out = git("commit", "-m", f"daily: {tag}")
    log(f"commit rc={rc} {out.splitlines()[0] if out else ''}")

    rc, out = git("push", "origin", "main")
    log(f"push main rc={rc} {out.splitlines()[-1] if out else ''}")

    # gh-pages
    wt = Path("/tmp/newsinai-gh")
    subprocess.run(["bash", "-c", f"rm -rf {wt} && git worktree add --detach {wt} >/dev/null 2>&1"], cwd=ROOT)
    if wt.exists():
        subprocess.run(["bash", "-c", "git checkout gh-pages >/dev/null 2>&1 && rm -rf daily && mkdir -p daily && cp -r "
                                     f"{ROOT}/site/. daily/ && touch .nojekyll"], cwd=wt)
        subprocess.run(["git", "add", "-A"], cwd=wt)
        subprocess.run(["git", "-c", "user.name=Vist233", "-c", "user.email=Vist233@users.noreply.github.com",
                        "commit", "-m", f"publish: {day}"], cwd=wt, capture_output=True)
        r2 = subprocess.run(["git", "push", "origin", "gh-pages"], cwd=wt, capture_output=True, text=True)
        log(f"push gh-pages rc={r2.returncode} {(r2.stdout + r2.stderr).strip().splitlines()[-1] if (r2.stdout or r2.stderr) else ''}")
        subprocess.run(["bash", "-c", f"cd {ROOT} && git worktree remove {wt} --force"], capture_output=True)

    log(f"=== 完成，降级项 {len(errors)} ===")
    if errors:
        from collections import Counter
        log("降级明细: " + ", ".join(f"{k}×{v}" for k, v in Counter(errors).most_common()))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
