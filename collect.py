#!/usr/bin/env python3
"""我自己的一手采集：Hacker News / GitHub Trending / arXiv / YouTube。

只抓原始条目，不做摘要——摘要与判断由助手写进 content/YYYY-MM-DD.json。
输出：raw/YYYY-MM-DD.json
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROXY = "http://127.0.0.1:7897"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36"


def fetch(url: str, timeout: int = 40) -> str:
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": PROXY, "https": PROXY})
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with opener.open(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", "replace")


def hacker_news(limit: int = 12) -> list[dict]:
    """HN 首页 + 近 24h 高分（Algolia，无 key）。"""
    data = json.loads(fetch("https://hn.algolia.com/api/v1/search?tags=front_page&hitsPerPage=40"))
    cutoff = datetime.now(timezone.utc) - timedelta(hours=30)
    out = []
    for h in data.get("hits", []):
        ts = h.get("created_at_i") or 0
        when = datetime.fromtimestamp(ts, timezone.utc)
        if when < cutoff:
            continue
        url = h.get("url") or f"https://news.ycombinator.com/item?id={h.get('objectID')}"
        out.append({
            "title": (h.get("title") or "").strip(),
            "url": url,
            "points": h.get("points") or 0,
            "comments": h.get("num_comments") or 0,
            "published": when.isoformat(),
            "hn_id": h.get("objectID"),
        })
    out.sort(key=lambda x: -x["points"])
    return out[:limit]


def github_trending(limit: int = 10) -> list[dict]:
    html = fetch("https://github.com/trending?since=daily")
    rows = re.findall(r'<article class="Box-row">(.*?)</article>', html, re.S)
    out = []
    for row in rows[:limit]:
        name = re.search(r'<h2[^>]*>.*?<a[^>]*href="/([^"]+)"', row, re.S)
        desc = re.search(r'<p class="col-9[^"]*"[^>]*>(.*?)</p>', row, re.S)
        lang = re.search(r'itemprop="programmingLanguage">(.*?)</span>', row, re.S)
        stars = re.search(r'([\d,]+)\s*stars today', row, re.S)
        if not name:
            continue
        out.append({
            "repo": name.group(1).strip(),
            "desc": re.sub(r"<[^>]+>", "", desc.group(1)).strip() if desc else "",
            "language": lang.group(1).strip() if lang else "",
            "stars_today": stars.group(1) if stars else "",
            "url": "https://github.com/" + name.group(1).strip(),
        })
    return out


def arxiv(limit: int = 12) -> list[dict]:
    q = ("http://export.arxiv.org/api/query?search_query="
         "cat:cs.AI+OR+cat:cs.LG+OR+cat:cs.CL+OR+cat:cs.SE"
         f"&sortBy=submittedDate&sortOrder=descending&max_results={limit * 3}")
    xml = fetch(q, timeout=60)
    entries = re.findall(r"<entry>(.*?)</entry>", xml, re.S)
    out = []
    for e in entries:
        title = re.search(r"<title>(.*?)</title>", e, re.S)
        link = re.search(r'<id>(.*?)</id>', e, re.S)
        pub = re.search(r"<published>(.*?)</published>", e, re.S)
        summ = re.search(r"<summary>(.*?)</summary>", e, re.S)
        if not title or not link:
            continue
        out.append({
            "title": re.sub(r"\s+", " ", title.group(1)).strip(),
            "url": link.group(1).strip(),
            "published": pub.group(1).strip() if pub else "",
            "abstract": re.sub(r"\s+", " ", summ.group(1)).strip()[:900] if summ else "",
        })
        if len(out) >= limit:
            break
    return out


def youtube(queries: list[str], per: int = 4) -> list[dict]:
    """按上传日期排序搜，取真实 upload_date。"""
    out, seen = [], set()
    for q in queries:
        url = ("https://www.youtube.com/results?search_query="
               + urllib.parse.quote(q) + "&sp=CAI%3D")
        try:
            html = fetch(url)
        except Exception:
            continue
        ids = re.findall(r'"videoId":"([\w-]{11})"', html)
        for vid in dict.fromkeys(ids):
            if vid in seen or len(out) >= per * len(queries):
                continue
            seen.add(vid)
            try:
                raw = subprocess.run(
                    ["yt-dlp", "--dump-single-json", "--no-warnings", "--skip-download",
                     f"https://www.youtube.com/watch?v={vid}"],
                    capture_output=True, text=True, timeout=90,
                    env={"https_proxy": PROXY, "http_proxy": PROXY, "PATH": "/usr/local/bin:/usr/bin:/bin:" + str(Path.home() / ".local/bin")},
                )
                meta = json.loads(raw.stdout or "{}")
            except Exception:
                continue
            if not meta.get("upload_date"):
                continue
            out.append({
                "title": meta.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={vid}",
                "channel": meta.get("channel") or meta.get("uploader", ""),
                "duration_s": meta.get("duration") or 0,
                "views": meta.get("view_count") or 0,
                "upload_date": meta.get("upload_date"),
                "description": (meta.get("description") or "")[:600],
            })
            if len([v for v in out if v["url"] not in seen]) >= per:
                break
    return out


if __name__ == "__main__":
    import urllib.parse  # noqa: F401  (youtube() 里用)

    day = datetime.now().strftime("%Y-%m-%d")
    raw = {}
    for name, fn in (
        ("hacker_news", lambda: hacker_news(12)),
        ("github_trending", lambda: github_trending(10)),
        ("papers", lambda: arxiv(12)),
    ):
        try:
            raw[name] = fn()
            print(f"{name}: {len(raw[name])} 条")
        except Exception as exc:
            raw[name] = []
            print(f"{name}: 失败 {type(exc).__name__}: {exc}", file=sys.stderr)

    (ROOT / "raw").mkdir(exist_ok=True)
    out = ROOT / "raw" / f"{day}.json"
    out.write_text(json.dumps(raw, ensure_ascii=False, indent=1), encoding="utf-8")
    print("写入", out)
