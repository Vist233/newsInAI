#!/usr/bin/env python3
"""把每天的配套产物（方向雷达 / 岗位 / 宏观内参 / issue 日报）渲染进当日页面。

版式固定在这里，源文件只提供内容；缺哪份就整段跳过，不留空标题。
产物位置：
  方向雷达   /mnt/d/Basic/vc-radar/daily/<date>.md
  岗位       /mnt/d/Basic/jobs-radar/data/<date>.jsonl
  宏观内参   ~/.hermes/cron/output/01f82769861f/<date>_*.md
  issue 日报 ~/.hermes/cron/output/20ac16e0fd67/<date>_*.md
"""
from __future__ import annotations

import datetime as dt
import glob
import html
import json
import os
import re
from pathlib import Path

VC = Path("/mnt/d/Basic/vc-radar/daily")
JOBS = Path("/mnt/d/Basic/jobs-radar/data")
CRON = Path.home() / ".hermes" / "cron" / "output"
MACRO_JOB = CRON / "01f82769861f"
ISSUE_JOB = CRON / "20ac16e0fd67"


def esc(s: str) -> str:
    return html.escape(str(s), quote=False)


def _latest(dirpath: Path, date: str, suffix: str = ".md") -> Path | None:
    if not dirpath.exists():
        return None
    hits = sorted(dirpath.glob(f"{date}*{suffix}"))
    if hits:
        return hits[-1]
    hits = sorted(dirpath.glob(f"*{suffix}"))
    return hits[-1] if hits else None


def _strip_cron_header(text: str) -> str:
    if text.startswith("# Cron Job:"):
        parts = text.split("\n---\n", 1)
        return parts[1] if len(parts) > 1 else text
    return text


def _md_blocks(text: str):
    """把 markdown 粗切成 (标题, [行])，够用就行。"""
    blocks, cur = [], ("", [])
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.startswith("## "):
            if cur[0] or cur[1]:
                blocks.append(cur)
            cur = (re.sub(r"^##\s*", "", line).strip(), [])
        elif line.startswith("# "):
            if cur[0] or cur[1]:
                blocks.append(cur)
            cur = (re.sub(r"^#\s*", "", line).strip(), [])
        elif line.strip():
            cur[1].append(line.strip())
    if cur[0] or cur[1]:
        blocks.append(cur)
    return blocks


def _inline(s: str) -> str:
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', s)
    s = re.sub(r"(?<!\*)\*(?!\*)", "", s)      # 源里的单星号是坏 markdown，直接去掉
    return s


def _item(i: int, title: str, lines: list[str]) -> str:
    plain_title = re.sub(r"[*`]", "", title).strip()
    body = "".join(
        f'<div class="description">{_inline(x)}</div>'
        for x in lines
        if not x.startswith((">", "-")) and re.sub(r"[*`]", "", x).strip() != plain_title)
    bullets = [x.lstrip("- ").strip() for x in lines if x.startswith("- ")]
    if bullets:
        body += '<div class="description">' + "；".join(_inline(b) for b in bullets) + "</div>"
    quotes = [x.lstrip("> ").strip() for x in lines if x.startswith(">")]
    if quotes:
        body += "".join(f'<blockquote class="radar-quote">{_inline(q)}</blockquote>' for q in quotes if q)
    return (
        '<article class="item">'
        f'<div class="item-no">{i:02d}</div>'
        '<div class="item-main">'
        f'<div class="title-line"><span class="title-link">{_inline(title)}</span></div>'
        f"{body}"
        "</div></article>"
    )


def _section(no: str, title: str, subtitle: str, inner: str) -> str:
    return (
        "<section>"
        f'<div class="section-head"><span class="section-no">{no}</span><h2>{esc(title)}</h2></div>'
        f'<p class="section-subtitle">{esc(subtitle)}</p>'
        f'<div class="items">{inner}</div>'
        "</section>"
    )


def radar_html(date: str) -> str:
    p = VC / f"{date}.md"
    if not p.exists():
        cand = sorted(VC.glob("*.md"))
        if not cand:
            return ""
        p = cand[-1]
    blocks = _md_blocks(p.read_text(encoding="utf-8"))
    parts, i = [], 0
    for head, lines in blocks:
        if not head:
            continue
        label = "" if ("一句话" in head) else f'<p class="section-subtitle">{esc(head)}</p>'
        if label:
            parts.append(label)
        if "原句" in head:
            qs = [x.lstrip("> ").strip() for x in lines if x.startswith(">")]
            inner = "".join(f'<blockquote class="radar-quote">{_inline(q)}</blockquote>' for q in qs if q)
            if inner:
                parts.append(f'<p class="section-subtitle">{esc(head)}</p>{inner}')
            continue
        bullets = [x for x in lines if x.startswith("- ") or re.match(r"^\d+\.", x)]
        for b in bullets:
            i += 1
            b = re.sub(r"^-\s*|^\d+\.\s*", "", b)
            if "：—" in b:
                parts.append(f'<article class="item"><div class="item-main"><div class="description">{_inline(b)}</div></div></article>')
            else:
                parts.append(_item(i, b.split("—")[0].strip(), [b]))
        plain = [x for x in lines if x and not x.startswith(("-", ">")) and not re.match(r"^\d+\.", x)]
        if plain and not bullets:
            parts.append(f'<article class="item"><div class="item-main"><div class="description">{_inline(plain[0])}</div></div></article>')
    if not parts:
        return ""
    return _section("09", "方向雷达", "钱去哪 / 我能做什么 / 名人原句", "".join(parts))


def jobs_html(date: str) -> str:
    p = JOBS / f"{date}.jsonl"
    if not p.exists():
        cand = sorted(JOBS.glob("*.jsonl"))
        if not cand:
            return ""
        p = cand[-1]
    rows, seen = [], set()
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        key = (r.get("title") or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(r)
    if not rows:
        return ""
    by_dir: dict[str, list] = {}
    for r in rows:
        by_dir.setdefault(r.get("direction") or "其他", []).append(r)
    parts = [f'<div class="description">今日抓取 {len(rows)} 条，按方向归并（智联）</div>']
    for d, rs in sorted(by_dir.items(), key=lambda kv: -len(kv[1]))[:6]:
        parts.append(f'<div class="description"><strong>{esc(d)}</strong>（{len(rs)} 条）</div>')
        for r in rs[:3]:
            t = esc(r.get("title", ""))[:60]
            meta = " · ".join(x for x in [r.get("company", ""), r.get("area", ""), r.get("salary", "")] if x and x != "**-**元")
            parts.append(f'<div class="description">· <a href="{esc(r.get("url",""))}">{t}</a> — {esc(meta)}</div>')
    return _section("10", "岗位雷达", "在招岗位按方向归并，只放当天的", "".join(parts))


def cron_digest_html(date: str, job_dir: Path, no: str, title: str, sub: str, limit: int = 8) -> str:
    p = _latest(job_dir, date)
    if not p:
        return ""
    text = _strip_cron_header(p.read_text(encoding="utf-8", errors="replace"))
    lines = []
    for raw in text.splitlines():
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("---"):
            continue
        s = s.replace("*", "")
        s = re.sub(r"^[-*]\s*", "", s)
        s = re.sub(r"^\d+[.)]\s*", "", s)
        if len(s) < 6 or "只读拉取" in s or re.search(r"日报\s*·\s*\d{4}", s):
            continue
        lines.append(s)
        if len(lines) >= limit:
            break
    if not lines:
        return ""
    inner = "".join(f'<div class="description">{_inline(x)}</div>' for x in lines)
    return _section(no, title, sub, inner)


def build(date: str | None = None) -> str:
    date = date or dt.date.today().isoformat()
    return "".join([
        radar_html(date),
        jobs_html(date),
        cron_digest_html(date, MACRO_JOB, "11", "宏观内参", "政策与科技商业，只留结论", 6),
        cron_digest_html(date, ISSUE_JOB, "12", "Issue 日报", "开源仓库里真实在痛的地方", 6),
    ])


if __name__ == "__main__":
    out = build()
    print(f"生成 {len(out)} 字符")
    for tag in ("09", "10", "11", "12"):
        print(tag, "有" if f'section-no">{tag}' in out else "无")
