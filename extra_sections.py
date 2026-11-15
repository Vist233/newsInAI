#!/usr/bin/env python3
"""每日配套产物 → 当日页面：方向雷达 / 岗位雷达 / 宏观内参 / Issue 日报。

统一格式：四个小节共用同一套「台账行」——左侧 190px 标签，右侧一句说明 + 等宽小标签，
行间只用 1px 细线；没有卡片、圆角、阴影、底色块。signal 色只留给小节编号。

详略：方向雷达 3 条钱 + 2 个项目 + 2 句原话；岗位 5 个方向各 1 条；宏观 / Issue 各 4 条。
超出的截断，宁可少给。
"""
from __future__ import annotations

import datetime as dt
import html
import json
import re
from pathlib import Path

VC = Path("/mnt/d/Basic/vc-radar/daily")
JOBS = Path("/mnt/d/Basic/jobs-radar/data")
CRON = Path.home() / ".hermes" / "cron" / "output"
MACRO_JOB = CRON / "01f82769861f"
ISSUE_JOB = CRON / "20ac16e0fd67"


def esc(s: str) -> str:
    return html.escape(str(s), quote=False)


def cut(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s if len(s) <= n else s[: n - 1].rstrip("，。；、： ") + "…"


def _inline(s: str) -> str:
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    s = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', s)
    return s.replace("*", "")


def _latest(dirpath: Path, date: str, suffix: str = ".md") -> Path | None:
    if not dirpath.exists():
        return None
    hits = sorted(dirpath.glob(f"{date}*{suffix}")) or sorted(dirpath.glob(f"*{suffix}"))
    return hits[-1] if hits else None


def _strip_cron_header(text: str) -> str:
    if text.startswith("# Cron Job:"):
        parts = text.split("\n---\n", 1)
        return parts[1] if len(parts) > 1 else text
    return text


# ---------- 统一组件 ----------

def _section(no: str, title: str, subtitle: str, body: str) -> str:
    return (
        "<section>"
        f'<div class="section-head"><span class="section-no">{no}</span><h2>{esc(title)}</h2></div>'
        f'<p class="section-subtitle">{esc(subtitle)}</p>'
        f'<div class="ledger">{body}</div>'
        "</section>"
    )


def _cap(i: int, label: str) -> str:
    return f'<div class="led-cap"><span>{i:02d}</span>{esc(label)}</div>'


def _row(key: str, note: str = "", tags: list[str] | None = None, mono_key: bool = False) -> str:
    cls = "led-key led-key-mono" if mono_key else "led-key"
    note_html = f"<p>{note}</p>" if note else ""
    clean = [t for t in (tags or []) if t and t.strip()]
    tag_html = ""
    if clean:
        tag_html = '<div class="led-tags">' + "".join(f"<span>{_inline(t)}</span>" for t in clean) + "</div>"
    return (f'<div class="led-row"><div class="{cls}">{_inline(key)}</div>'
            f'<div class="led-val">{note_html}{tag_html}</div></div>')


def _quote(text: str, cite: str, url: str = "") -> str:
    src = esc(cite)
    if url:
        src += f' · <a href="{esc(url)}">原文</a>'
    return f'<blockquote class="led-quote">{_inline(cut(text, 140))}<cite>{src}</cite></blockquote>'


# ---------- 09 方向雷达 ----------

def radar_html(date: str) -> str:
    p = VC / f"{date}.md"
    if not p.exists():
        cand = sorted(VC.glob("*.md"))
        if not cand:
            return ""
        p = cand[-1]

    blocks, cur = [], None
    for raw in p.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^#{2,3}\s*(.+)$", raw.strip())
        if m:
            cur = [re.sub(r"^[一二三四五]、", "", m.group(1)).strip(), []]
            blocks.append(cur)
        elif cur is not None and raw.strip():
            cur[1].append(raw)

    segs, idx = [], 0
    for head, lines in blocks:
        if "原句" in head:
            quotes, buf = [], []
            for line in lines + [">"]:
                s = line.strip()
                if s.startswith(">"):
                    t = s.lstrip(">").strip()
                    if t:
                        buf.append(t)
                    continue
                if buf:
                    body = buf[0]
                    cite = next((x.lstrip("— ").strip() for x in buf[1:] if x.startswith("—")), "")
                    url = next((x for x in buf[1:] if x.startswith("http")), "")
                    quotes.append(_quote(body, cite, url))
                    buf = []
                if len(quotes) >= 2:
                    break
            if quotes:
                idx += 1
                segs.append((_cap(idx, head), "".join(quotes)))
            continue

        if "一句话" in head:
            text = " ".join(x.strip() for x in lines if x.strip())
            if text:
                idx += 1
                segs.append((_cap(idx, "一句话"), f'<p class="led-line">{_inline(cut(text, 68))}</p>'))
            continue

        rows, current = [], None
        limit = 3 if "钱" in head else 2
        for line in lines:
            s = line.strip()
            if re.match(r"^\d+\.\s", s):
                s = re.sub(r"^\d+\.\s*", "", s)
                name, _, why = s.partition("—")
                current = {"key": name.strip(), "why": why.strip(), "tags": [], "fields": []}
                rows.append(current)
                continue
            if re.match(r"^[-*]\s*\*\*.+\*\*\s*[：:]", s):
                m = re.match(r"^[-*]\s*\*\*(.+?)\*\*\s*[：:]\s*(.*)$", s)
                if m:
                    current = {"key": m.group(1).strip(), "why": m.group(2).strip(),
                               "tags": [], "fields": []}
                    rows.append(current)
                continue
            if s.startswith(("- ", "  - ")) and current is not None:
                item = s.lstrip("- ").strip()
                fm = re.match(r"^(.{1,8})[：:]\s*(.+)$", item)
                if fm and not item.startswith("**"):
                    current["fields"].append(f"{fm.group(1).strip()} {fm.group(2).strip()}")
                else:
                    current["tags"].append(item)
        if not rows:
            continue
        idx += 1
        body = []
        for r in rows[:limit]:
            fields = [cut(f, 34) for f in r["fields"][:2]]
            if fields:
                body.append(_row(r["key"], cut(r["why"], 32), fields, mono_key=True))
            else:
                body.append(_row(r["key"], cut(r["why"], 40), r["tags"][:3]))
        segs.append((_cap(idx, head), "".join(body)))

    if not segs:
        return ""
    return _section("09", "方向雷达", "钱去哪 / 能做什么 / 名人原句",
                    "".join(c + b for c, b in segs))


# ---------- 10 岗位雷达 ----------

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
        k = (r.get("title") or "").strip()
        if not k or k in seen:
            continue
        seen.add(k)
        rows.append(r)
    if not rows:
        return ""

    by_dir: dict[str, list] = {}
    for r in rows:
        by_dir.setdefault(r.get("direction") or "其他", []).append(r)

    body = [_cap(0, f"今日 {len(rows)} 条 · {len(by_dir)} 个方向")]
    for d, rs in sorted(by_dir.items(), key=lambda kv: -len(kv[1]))[:5]:
        first = rs[0]
        title = f'<a href="{esc(first.get("url",""))}">{esc(cut(first.get("title",""), 26))}</a>'
        meta = " · ".join(x for x in [first.get("company", ""), first.get("area", "")] if x)
        note = f"{len(rs)} 条 · {title}" + (
            f'<span class="led-dim"> {esc(cut(meta, 22))}</span>' if meta else "")
        body.append(f'<div class="led-row"><div class="led-key">{esc(d)}</div>'
                    f'<div class="led-val"><p>{note}</p></div></div>')
    return _section("10", "岗位雷达", "只放当天在招，按方向归并", "".join(body))


# ---------- 11 / 12 简报 ----------

def cron_digest_html(date: str, job_dir: Path, no: str, title: str, sub: str, limit: int = 4) -> str:
    """宏观内参：每条「标签：结论」拆成左标签 + 右一句。"""
    p = _latest(job_dir, date)
    if not p:
        return ""
    text = _strip_cron_header(p.read_text(encoding="utf-8", errors="replace"))
    rows = []
    for raw in text.splitlines():
        s = raw.strip().replace("*", "")
        if not s or s.startswith(("#", "---", "★", "|")):
            continue
        s = re.sub(r"^[-•]\s*", "", s)
        s = re.sub(r"^\d+[.)]\s*", "", s)
        if len(s) < 12 or re.match(r"^(Job ID|Run Time|Mode|Cron Job|只读拉取)", s):
            continue
        label, sep, rest = s.partition("：")
        if sep and len(label) <= 12:
            rows.append(_row(label.strip(), cut(rest.strip(), 56)))
        else:
            rows.append(_row(f"{len(rows)+1:02d}", cut(s, 60), mono_key=True))
        if len(rows) >= limit:
            break
    if not rows:
        return ""
    return _section(no, title, sub, "".join(rows))


def issues_html(date: str, job_dir: Path, no: str, title: str, sub: str, limit: int = 5) -> str:
    """Issue 日报：仓库名做左标签，右侧放最新一条未被 PR 关联的 issue。"""
    p = _latest(job_dir, date)
    if not p:
        return ""
    text = _strip_cron_header(p.read_text(encoding="utf-8", errors="replace"))
    rows, repo, skip_pr_section = [], "", False
    counts: dict[str, int] = {}
    for raw in text.splitlines():
        s = raw.strip().replace("*", "")
        if not s:
            continue
        m = re.match(r"^#{2,4}\s*([^`]+?)\s*`?([\w.-]+/[\w.-]+)`?$", s)
        if m:
            repo = m.group(1).strip() or m.group(2).split("/")[-1]
            skip_pr_section = False
            continue
        if "已有 PR" in s:
            skip_pr_section = True
            continue
        if skip_pr_section:
            continue
        m = re.match(r"^#(\d+)\s*\[(.{1,6})\]\s*(.+?)\s*\((\d+)评[^)]*\)$", s)
        if m and repo:
            if counts.get(repo, 0) >= 2:      # 每个仓库最多两条，避免一家占满
                continue
            counts[repo] = counts.get(repo, 0) + 1
            num, tag, body, comments = m.groups()
            rows.append(_row(repo, f'<a href="#">#{num}</a> [{esc(tag)}] {esc(cut(body, 44))}'
                                   f'<span class="led-dim"> {comments} 评</span>', mono_key=True))
        if len(rows) >= limit:
            break
    if not rows:
        return ""
    return _section(no, title, sub, "".join(rows))


def build(date: str | None = None) -> str:
    date = date or dt.date.today().isoformat()
    return "".join([
        radar_html(date),
        jobs_html(date),
        cron_digest_html(date, MACRO_JOB, "11", "宏观内参", "政策与科技商业，只留结论"),
        issues_html(date, ISSUE_JOB, "12", "Issue 日报", "开源仓库里真实在痛的地方"),
    ])


CSS = """
  .ledger { border-top: 1px solid var(--line-strong); }
  .led-cap {
    display: flex; gap: 10px; align-items: baseline; padding: 16px 0 8px;
    font-family: var(--font-mono); font-size: 10.5px; letter-spacing: .14em;
    text-transform: uppercase; color: var(--muted);
  }
  .led-cap span { color: var(--ink); }
  .led-row {
    display: grid; grid-template-columns: 190px minmax(0, 1fr);
    gap: 20px; padding: 12px 0; border-top: 1px solid var(--line); align-items: start;
  }
  .led-key { font-size: 14px; font-weight: 600; line-height: 1.55; color: var(--ink); }
  .led-key-mono {
    font-family: var(--font-mono); font-weight: 400; font-size: 12px;
    color: var(--muted); padding-top: 3px;
  }
  .led-val { min-width: 0; }
  .led-val p { margin: 0; font-size: 13.5px; line-height: 1.65; color: var(--muted); }
  .led-val a { color: var(--ink); text-decoration: none; border-bottom: 1px solid var(--line); }
  .led-val a:hover { border-bottom-color: var(--ink); }
  .led-dim { color: var(--muted); font-size: 12px; }
  .led-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 7px; }
  .led-tags span {
    font-family: var(--font-mono); font-size: 10.5px; color: var(--muted);
    border: 1px solid var(--line); padding: 1px 6px;
  }
  .led-quote {
    margin: 12px 0 0; padding: 0 0 0 16px; border-left: 2px solid var(--ink);
    font-size: 14.5px; line-height: 1.7; color: var(--ink);
  }
  .led-quote cite {
    display: block; margin-top: 7px; font-style: normal;
    font-family: var(--font-mono); font-size: 11px; color: var(--muted);
  }
  .led-quote cite a { color: var(--muted); text-decoration: none; border-bottom: 1px solid var(--line); }
  .led-line { margin: 14px 0 0; font-size: 15px; line-height: 1.7; color: var(--ink); }

  @media (max-width: 760px) {
    .led-row { grid-template-columns: 1fr; gap: 5px; }
    .led-key-mono { padding-top: 0; }
  }
"""


if __name__ == "__main__":
    out = build()
    print(f"生成 {len(out)} 字符 · 行数 {out.count('led-row')}")
    for tag in ("09", "10", "11", "12"):
        print(tag, "有" if f'section-no">{tag}' in out else "无")
