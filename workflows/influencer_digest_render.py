from __future__ import annotations

import json
import re
import shutil
from dataclasses import asdict
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Dict, List
from xml.sax.saxutils import escape as xml_escape
from zoneinfo import ZoneInfo

from workflows.influencer_digest_models import (
    BookChapterRecommendation,
    DigestItem,
    MovieRecommendation,
    clean_brief_text,
    clean_generated_summary,
    sanitize_digest_item,
    strip_title_prefix,
)

PROJECT_ROOT = Path(__file__).parent.parent
LOCAL_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_SITE_DIR = PROJECT_ROOT / "output" / "site"
SITE_URL = "https://news.zhangyvjing.com"
ISSUE_MONITOR_URL = f"{SITE_URL}/issue-monitor/latest.html"
ISSUE_MONITOR_QUEUE_URL = f"{ISSUE_MONITOR_URL}?view=queue"
ARXIV_CATEGORY_RE = re.compile(r"^[a-z]+(?:-[a-z]+)*\.[A-Z][A-Za-z-]*$")


class SiteRenderer:
    def __init__(self, site_dir: Path = DEFAULT_SITE_DIR):
        self.site_dir = site_dir

    def render(
        self,
        items: List[DigestItem],
        summary_md: str,
        movie: MovieRecommendation,
        book: BookChapterRecommendation | None = None,
        *,
        issue_monitor: Dict[str, Any] | None = None,
    ) -> Dict[str, Path]:
        today = datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")
        reports_dir = self.site_dir / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)
        self.site_dir.mkdir(parents=True, exist_ok=True)

        # Copy favicon
        logo_src = PROJECT_ROOT / "assets" / "logo.png"
        if logo_src.exists():
            shutil.copy(logo_src, self.site_dir / "logo.png")

        items = [sanitize_digest_item(item) for item in items]
        section_counts: Dict[str, int] = {}
        item_payload = []
        for item in items:
            section_counts[item.kind] = section_counts.get(item.kind, 0) + 1
            row = asdict(item)
            row["categories"] = self._visible_categories(row.get("categories", []))
            row["_number"] = f"{section_counts[item.kind]:02d}"
            item_payload.append(row)

        payload = {
            "date": today,
            "summary": clean_generated_summary(
                summary_md,
                require_cjk=True,
                minimum_cjk=24,
            ),
            "movie": asdict(movie),
            "book": asdict(book) if book else None,
            "issue_monitor": issue_monitor,
            "items": item_payload,
        }
        json_path = self.site_dir / "latest.json"
        report_path = reports_dir / f"{today}.html"
        index_path = self.site_dir / "index.html"
        rss_path = self.site_dir / "rss.xml"

        json_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        html = self._html(payload)
        rss = self._rss(payload)
        report_path.write_text(html, encoding="utf-8")
        index_path.write_text(html, encoding="utf-8")
        rss_path.write_text(rss, encoding="utf-8")
        return {
            "json": json_path,
            "report": report_path,
            "index": index_path,
            "rss": rss_path,
        }

    def _html(self, payload: Dict[str, Any]) -> str:
        payload = self._sanitize_payload(payload)
        sections = [
            ("news", "02", "Worth Reading", "我的挑选 · 今日值得看"),
            ("hacker_news", "03", "Hacker News", ""),
            ("github_trending", "04", "GitHub Trending", "Daily · Top 10"),
            ("youtube", "05", "YouTube", ""),
            ("x", "06", "X / Twitter", ""),
            ("bilibili", "07", "Bilibili", ""),
            ("paper", "08", "Papers", ""),
        ]
        section_html = "\n".join(
            self._section_html(kind, no, title, subtitle, payload["items"])
            for kind, no, title, subtitle in sections
            if any(item.get("kind") == kind for item in payload["items"])
        )
        issue_monitor_html = (
            self._issue_monitor_html(payload.get("issue_monitor"))
            if payload.get("issue_monitor")
            else ""
        )
        movie = payload["movie"]
        book = payload.get("book") or self._fallback_book()
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Daily Brief · {escape(payload["date"])}</title>
  <link rel="icon" href="/logo.png">
  <style>
    :root {{
      --paper:#f1f0ec;
      --field:#e6e3dc;
      --ink:#111111;
      --muted:#6e6c66;
      --line:#c9c5bc;
      --line-strong:#1c1c1c;
      --signal:#d8ff3e;
      --signal-soft:rgba(216,255,62,.34);
      --font-sans:Inter,"Helvetica Neue",Arial,"PingFang SC","Microsoft YaHei",sans-serif;
      --font-mono:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
      --item-no-width:52px;
      --item-gap:18px;
    }}
    * {{ box-sizing:border-box; }}
    body {{
      margin:0;
      font-family:var(--font-sans);
      background:
        linear-gradient(rgba(201,197,188,.34) 1px, transparent 1px),
        linear-gradient(90deg, rgba(201,197,188,.34) 1px, transparent 1px),
        var(--paper);
      background-size:48px 48px,48px 48px,auto;
      color:var(--ink);
    }}
    main {{
      max-width:1120px;
      margin:56px auto;
      padding:42px 20px 72px;
      background:var(--paper);
      box-shadow:0 0 0 12px var(--paper);
      position:relative;
    }}
    header {{
      border-bottom:1px solid var(--line-strong);
      padding-bottom:28px;
      margin-bottom:0;
    }}
    .eyebrow,.date,.meta,.tags,.section-no {{
      font-family:var(--font-mono);
      color:var(--muted);
      font-size:12px;
      letter-spacing:0;
    }}
    .identity {{
      font-family:var(--font-sans);
      color:var(--ink);
      font-size:clamp(36px,8vw,86px);
      line-height:.92;
      font-weight:800;
      margin:8px 0 6px;
      letter-spacing:0;
    }}
    h1 {{ font-size:clamp(32px,7vw,74px); line-height:.92; margin:0; letter-spacing:0; font-weight:800; }}
    .hollow {{ color:transparent; -webkit-text-stroke:1.2px var(--ink); }}
    h2 {{ font-size:18px; margin:0; }}
    section {{ border-top:1px solid var(--line-strong); padding:34px 0; background:var(--paper); }}
    header + section {{ border-top:0; }}
    .section-head {{ display:flex; align-items:center; gap:12px; margin-bottom:16px; }}
    .section-no {{
      background:var(--signal);
      color:var(--ink);
      padding:2px 6px;
      display:inline-flex;
      align-items:center;
      justify-content:center;
      min-width:30px;
      height:20px;
      transform:translateY(-1px);
    }}
    .summary {{
      white-space:pre-wrap;
      line-height:1.75;
      font-size:16px;
    }}
    .section-subtitle {{ margin:0 0 16px 0; color:var(--muted); font-size:13px; }}
    .feature-card {{
      display:grid;
      grid-template-columns:260px minmax(0,1fr);
      gap:24px;
      align-items:stretch;
    }}
    .feature-stack {{
      display:grid;
      gap:22px;
    }}
    .feature-art {{
      min-height:150px;
      border:1px solid var(--line-strong);
      background:
        linear-gradient(135deg, rgba(216,255,62,.52), transparent 42%),
        linear-gradient(var(--line) 1px, transparent 1px),
        linear-gradient(90deg, var(--line) 1px, transparent 1px),
        var(--field);
      background-size:auto, 28px 28px, 28px 28px, auto;
      padding:14px;
      display:flex;
      flex-direction:column;
      justify-content:space-between;
    }}
    .feature-art-title {{
      font-size:28px;
      line-height:.98;
      font-weight:800;
    }}
    .feature-art-meta {{
      font-family:var(--font-mono);
      font-size:12px;
      color:var(--ink);
    }}
    .book-art {{
      background:
        linear-gradient(135deg, rgba(17,17,17,.08), transparent 44%),
        linear-gradient(var(--line) 1px, transparent 1px),
        linear-gradient(90deg, var(--line) 1px, transparent 1px),
        var(--field);
      background-size:auto, 28px 28px, 28px 28px, auto;
    }}
    .movie-info p {{ margin:0 0 10px; }}
    .movie-title {{ font-size:20px; line-height:1.25; }}
    .movie-reason {{ line-height:1.75; max-width:720px; }}
    .book-title {{ font-size:20px; line-height:1.25; margin:0 0 10px; }}
    .book-chapter {{ margin:0 0 10px; color:var(--ink); line-height:1.5; }}
    .book-reason {{ margin:0; line-height:1.75; max-width:720px; }}
    .items {{ border-top:0; }}
    .item {{
      display:grid;
      grid-template-columns:var(--item-no-width) minmax(0,1fr);
      gap:var(--item-gap);
      border-bottom:1px solid var(--line);
      padding:16px 0;
      align-items:start;
    }}
    .item:last-child {{
      border-bottom:0;
      padding-bottom:0;
    }}
    .item-no {{
      font-family:var(--font-mono);
      color:var(--muted);
      font-size:13px;
      line-height:1.35;
      padding-top:2px;
    }}
    .item-main {{ min-width:0; }}
    .title-line {{
      display:flex;
      align-items:baseline;
      justify-content:space-between;
      gap:14px;
      width:100%;
    }}
    .title-link {{
      color:var(--ink);
      font-size:17px;
      line-height:1.35;
      text-decoration-thickness:1px;
      text-underline-offset:4px;
      flex:1;
      min-width:0;
    }}
    .item a:hover {{ background:var(--signal-soft); }}
    .inline-time {{
      flex:0 0 auto;
      white-space:nowrap;
      text-align:right;
    }}
    .item a {{ color:var(--ink); }}
    .item a:hover {{ background:var(--signal-soft); }}
    .source-line {{
      margin-top:6px;
      min-height:16px;
    }}
    .media-layout {{
      display:grid;
      grid-template-columns:220px minmax(0,1fr);
      gap:24px;
      align-items:stretch;
    }}
    .media-body {{
      min-height:100%;
      display:flex;
      flex-direction:column;
    }}
    .video-meta {{
      margin-top:auto;
    }}
    .thumb {{
      display:block;
      width:100%;
      aspect-ratio:16/9;
      object-fit:cover;
      border:1px solid var(--line-strong);
      background:var(--field);
    }}
    .description {{
      margin-top:8px;
      color:var(--muted);
      font-size:14px;
      line-height:1.65;
      display:-webkit-box;
      -webkit-line-clamp:3;
      -webkit-box-orient:vertical;
      overflow:hidden;
    }}
    .monitor-link-row {{
      display:grid;
      grid-template-columns:minmax(0,1fr) auto;
      gap:20px;
      align-items:center;
    }}
    .monitor-title {{
      font-size:18px;
      line-height:1.25;
      margin:0 0 5px;
    }}
    .monitor-overview {{
      color:var(--muted);
      font-size:14px;
      line-height:1.55;
      max-width:540px;
      margin:0;
    }}
    .monitor-facts {{
      display:grid;
      grid-template-columns:repeat(3,minmax(0,1fr));
      gap:10px;
      margin-top:14px;
      max-width:620px;
    }}
    .monitor-fact {{
      min-width:0;
      padding:10px 12px;
      border-top:2px solid var(--signal);
      background:var(--field);
    }}
    .monitor-fact-label {{
      display:block;
      color:var(--muted);
      font:10px/1.2 var(--font-mono);
      letter-spacing:.04em;
      text-transform:uppercase;
    }}
    .monitor-fact-value {{
      display:block;
      color:var(--ink);
      font-size:25px;
      font-weight:800;
      line-height:1.1;
      margin:5px 0 3px;
    }}
    .monitor-fact-copy {{
      display:block;
      color:var(--muted);
      font-size:12px;
      line-height:1.35;
    }}
    .monitor-link {{
      display:inline-flex;
      align-items:center;
      border:1px solid var(--ink);
      background:var(--field);
      color:var(--ink);
      padding:8px 10px;
      font:12px/1 var(--font-mono);
      text-decoration:none;
      max-width:100%;
      overflow-wrap:anywhere;
    }}
    .monitor-link:hover {{
      background:var(--signal);
      color:var(--ink);
    }}
    .brief-footer {{
          margin-top:42px;
          padding-top:18px;
          border-top:1px solid var(--line);
          display:flex;
          justify-content:center;
          align-items:center;
          font:12px/1 var(--font-mono);
        }}
        .brief-footer a {{
          color:var(--muted);
          text-decoration:none;
        }}
        .brief-footer a:hover {{
          color:var(--ink);
          text-decoration:underline;
          text-decoration-color:var(--signal);
          text-underline-offset:4px;
        }}
        .brief-footer .footer-sep {{
          color:var(--muted);
          margin: 0 10px;
          user-select:none;
          pointer-events:none;
        }}
        @media (max-width:720px) {{
          .brief-footer .footer-sep {{ margin: 0 8px; }}
        }}
    @media (max-width:720px) {{
      :root {{
        --item-no-width:38px;
      }}
      .title-line {{
        flex-direction:column;
        align-items:flex-start;
        gap:4px;
      }}
      .inline-time {{
        text-align:left;
      }}
      .media-layout {{ grid-template-columns:1fr; }}
      .feature-card {{ grid-template-columns:1fr; }}
      .monitor-link-row {{
        grid-template-columns:1fr;
        grid-template-areas:"action" "details";
      }}
      .monitor-copy {{ grid-area:details; }}
      .monitor-facts {{ grid-template-columns:repeat(3,minmax(0,1fr)); }}
      .monitor-link {{ grid-area:action; }}
      .monitor-link {{ justify-self:start; }}
    }}
  </style>
</head>
<body>
<main>
  <header>
    <div class="identity">ZhangYvJing's</div>
    <h1><span class="hollow">Daily Brief</span></h1>
  </header>
  <section class="feature-picks">
    <div class="section-head"><span class="section-no">00</span><h2>Film / Book Chapter</h2></div>
    <div class="feature-stack">
      <div class="feature-card">
        <div class="feature-art">
          <div class="feature-art-title">{escape(movie["title"])}</div>
          <div class="feature-art-meta">{escape(str(movie["year"]))} / {escape(movie["director"])}</div>
        </div>
        <div class="movie-info">
          <p class="movie-title"><strong>{escape(movie["title"])} ({movie["year"]})</strong> · {escape(movie["director"])}</p>
          <p class="movie-reason">{escape(movie["reason"])}</p>
        </div>
      </div>
      <div class="feature-card">
        <div class="feature-art book-art">
          <div class="feature-art-title">{escape(book["title"])}</div>
          <div class="feature-art-meta">{escape(book["author"])}</div>
        </div>
        <div class="movie-info">
          <p class="book-title"><strong>{escape(book["title"])}</strong> · {escape(book["author"])}</p>
          <p class="book-chapter">{escape(book["chapter"])}</p>
          <p class="book-reason">{escape(book["reason"])}</p>
        </div>
      </div>
    </div>
  </section>
  <section>
    <div class="section-head"><span class="section-no">01</span><h2>Insight</h2></div>
    <div class="summary">{escape(payload["summary"])}</div>
  </section>
  {section_html or "<section><p>今天没有新增条目。</p></section>"}
  {issue_monitor_html}
  <footer class="brief-footer">
    <a href="/history/">History</a>
    <span class="footer-sep">·</span>
    <a href="/rss.xml">RSS</a>
  </footer>
</main>
<script>
(function() {{
  function relative(iso) {{
    const then = new Date(iso);
    if (isNaN(then.getTime())) return iso;
    const diff = Math.floor((Date.now() - then.getTime()) / 1000);
    if (diff < 60) return 'just now';
    if (diff < 3600) return Math.floor(diff / 60) + ' min ago';
    if (diff < 86400) return Math.floor(diff / 3600) + ' hr ago';
    if (diff < 2592000) return Math.floor(diff / 86400) + ' d ago';
    const months = Math.floor(diff / 2592000);
    if (months < 12) return months + ' mo ago';
    return Math.floor(months / 12) + ' yr ago';
  }}
  document.querySelectorAll('.rel-time').forEach(el => {{
    const iso = el.getAttribute('datetime');
    if (iso) el.textContent = relative(iso);
  }});
}})();
</script>
</body>
</html>
"""

    def _fallback_book(self) -> Dict[str, Any]:
        return {
            "title": "The Pragmatic Programmer",
            "author": "David Thomas / Andrew Hunt",
            "chapter": "Chapter 1: A Pragmatic Philosophy",
            "reason": "A compact reset on ownership, taste, entropy, and being the kind of engineer whose work keeps improving after the first pass.",
            "tags": ["engineering", "craft", "judgment"],
        }

    def _rss(self, payload: Dict[str, Any]) -> str:
        report_url = f"{SITE_URL}/reports/{payload['date']}.html"
        latest_url = f"{SITE_URL}/"
        items = payload.get("items", [])
        summary = str(payload.get("summary", "")).strip()
        now = datetime.now(timezone.utc)
        pub_date = now.strftime("%a, %d %b %Y %H:%M:%S GMT")
        entries: List[str] = []

        if summary:
            entries.append(f"""    <item>
      <title>{xml_escape(payload["date"])} Daily Brief</title>
      <link>{xml_escape(report_url)}</link>
      <guid>{xml_escape(report_url)}</guid>
      <pubDate>{pub_date}</pubDate>
      <description>{xml_escape(summary)}</description>
    </item>""")

        for item in items[:40]:
            item_title = str(item.get("title", "")).strip()
            item_link = str(item.get("url", "")).strip() or latest_url
            item_summary = self._item_description(item)
            item_published = str(item.get("published", "")).strip()
            try:
                item_dt = datetime.fromisoformat(item_published)
            except ValueError:
                item_dt = now
            item_pub_date = item_dt.astimezone(timezone.utc).strftime(
                "%a, %d %b %Y %H:%M:%S GMT"
            )
            kind = str(item.get("kind", "")).strip()
            entries.append(f"""    <item>
      <title>{xml_escape(item_title)}</title>
      <link>{xml_escape(item_link)}</link>
      <guid>{xml_escape(item_link)}</guid>
      <category>{xml_escape(kind)}</category>
      <pubDate>{item_pub_date}</pubDate>
      <description>{xml_escape(item_summary)}</description>
    </item>""")

        entries_xml = "\n".join(entries)
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>ZhangYvJing's Daily Brief</title>
    <link>{SITE_URL}/</link>
    <description>Combined feed for Hacker News, GitHub Trending, YouTube, X/Twitter, Bilibili, and paper selections from the Daily Brief.</description>
    <language>en-us</language>
    <lastBuildDate>{pub_date}</lastBuildDate>
{entries_xml}
  </channel>
</rss>
"""

    def _section_html(
        self,
        kind: str,
        number: str,
        title: str,
        subtitle: str,
        items: List[Dict[str, Any]],
    ) -> str:
        rows = "\n".join(
            self._item_html(item) for item in items if item.get("kind") == kind
        )
        subtitle_html = (
            f'<p class="section-subtitle">{escape(subtitle)}</p>' if subtitle else ""
        )
        return f"""<section>
    <div class="section-head"><span class="section-no">{number}</span><h2>{escape(title)}</h2></div>
    {subtitle_html}
    <div class="items">{rows}</div>
  </section>"""

    def _sanitize_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        safe_payload = dict(payload)
        safe_payload["summary"] = clean_generated_summary(
            payload.get("summary"),
            require_cjk=True,
            minimum_cjk=24,
        )

        safe_items = []
        for raw_item in payload.get("items") or []:
            if not isinstance(raw_item, dict):
                continue
            categories = raw_item.get("categories") or []
            if isinstance(categories, str):
                categories = [
                    part.strip() for part in categories.split(",") if part.strip()
                ]
            item = DigestItem(
                kind=str(raw_item.get("kind") or ""),
                source_id=str(raw_item.get("source_id") or ""),
                source_name=str(raw_item.get("source_name") or ""),
                title=str(raw_item.get("title") or ""),
                url=str(raw_item.get("url") or ""),
                published=str(raw_item.get("published") or ""),
                summary=str(raw_item.get("summary") or ""),
                raw_text=str(raw_item.get("raw_text") or ""),
                categories=categories,
                priority=str(raw_item.get("priority") or "medium"),
                image_url=str(raw_item.get("image_url") or ""),
            )
            safe_item = dict(raw_item)
            safe_item.update(asdict(sanitize_digest_item(item)))
            safe_item["categories"] = self._visible_categories(
                safe_item.get("categories", [])
            )
            safe_items.append(safe_item)
        safe_payload["items"] = safe_items
        return safe_payload

    def _issue_monitor_html(self, status: Dict[str, Any] | None = None) -> str:
        status = status if isinstance(status, dict) else {}
        actionable = status.get("actionable")
        recheck = status.get("needs_recheck")
        state = str(status.get("state") or "unknown").lower()
        age = status.get("age_hours")
        ready_value = str(actionable) if isinstance(actionable, int) else "—"
        recheck_value = str(recheck) if isinstance(recheck, int) else "—"
        state_value = "Fresh" if state == "fresh" else "Check status"
        age_copy = (
            f"Updated {age:g}h ago"
            if isinstance(age, (int, float))
            else "Live status unavailable"
        )
        return f"""<section class="issue-monitor-link" aria-labelledby="issue-monitor-title">
    <div class="section-head"><span class="section-no">09</span><h2 id="issue-monitor-title">Issue Monitor</h2></div>
      <div class="monitor-link-row">
        <div class="monitor-copy">
          <div class="monitor-facts" aria-label="Issue Monitor live status">
            <div class="monitor-fact"><span class="monitor-fact-label">Ready now</span><span class="monitor-fact-value">{escape(ready_value)}</span><span class="monitor-fact-copy">Actionable issues</span></div>
            <div class="monitor-fact"><span class="monitor-fact-label">Needs review</span><span class="monitor-fact-value">{escape(recheck_value)}</span><span class="monitor-fact-copy">Awaiting a fresh check</span></div>
            <div class="monitor-fact"><span class="monitor-fact-label">Data status</span><span class="monitor-fact-value">{escape(state_value)}</span><span class="monitor-fact-copy">{escape(age_copy)}</span></div>
          </div>
        </div>
        <a class="monitor-link" href="{escape(ISSUE_MONITOR_QUEUE_URL)}" aria-label="打开 Issue Monitor 的 Agent Queue">
          <span>Open queue</span><span aria-hidden="true">↗</span>
        </a>
      </div>
    </section>"""

    def _item_html(self, item: Dict[str, Any]) -> str:
        number = item.get("_number", "")
        description = self._item_description(item)
        description_html = (
            f'<div class="description">{escape(description)}</div>'
            if description
            else ""
        )
        visible_tags = self._visible_categories(item.get("categories", []))
        is_hn = item.get("kind") in {"hacker_news", "github_trending"}
        is_paper = item.get("kind") == "paper"
        source_line = "" if (is_hn or is_paper) else escape(item.get("source_name", ""))
        source_html = (
            f'<div class="meta source-line">{source_line}</div>' if source_line else ""
        )
        tags_html = (
            f'<div class="meta source-line">{escape(", ".join(visible_tags))}</div>'
            if visible_tags
            else ""
        )
        title_block = (
            f'<div class="title-line"><a class="title-link" href="{escape(item["url"])}">'
            f"{escape(item['title'])}</a>"
            f'<span class="meta inline-time"><time class="rel-time" datetime="{escape(item["published"])}">'
            f"{escape(item['published'])}</time></span></div>"
        )
        if item.get("kind") in {"youtube", "bilibili"}:
            image = item.get("image_url") or ""
            image_html = (
                f'<a href="{escape(item["url"])}"><img class="thumb" src="{escape(image)}" '
                f'alt="" loading="lazy" referrerpolicy="no-referrer"></a>'
                if image
                else '<div class="thumb"></div>'
            )
            return f"""<article class="item">
  <div class="item-no">{escape(str(number))}</div>
  <div class="item-main">
    <div class="media-layout">
      <div>{image_html}</div>
      <div class="media-body">
        {title_block}
        {description_html}
        <div class="video-meta">{tags_html}</div>
      </div>
    </div>
  </div>
</article>"""
        return f"""<article class="item">
  <div class="item-no">{escape(str(number))}</div>
  <div class="item-main">
    {title_block}
    {source_html}
    {description_html}
    {tags_html}
  </div>
</article>"""

    def _visible_categories(self, categories: List[str]) -> List[str]:
        hidden = {"technology", "hacker_news", "ai_news"}
        visible = []
        for raw_category in categories or []:
            category = str(raw_category).strip()
            if (
                not category
                or category in hidden
                or ARXIV_CATEGORY_RE.fullmatch(category)
            ):
                continue
            visible.append(category)
        return visible

    def _item_description(self, item: Dict[str, Any]) -> str:
        summary = clean_brief_text(item.get("summary"))
        is_generated_summary = item.get("kind") in {"paper", "github_trending"} or (
            item.get("kind") == "hacker_news" and item.get("source_id") != "smol_ai"
        )
        if is_generated_summary:
            summary = clean_generated_summary(
                summary,
                require_cjk=True,
                minimum_cjk=60,
                maximum_cjk=220,
            )
        raw_text = clean_brief_text(item.get("raw_text"))
        if item.get("kind") in {"hacker_news", "github_trending", "paper"}:
            return summary
        if item.get("kind") in {"youtube", "bilibili"} and not summary:
            return strip_title_prefix(raw_text, str(item.get("title", "")))
        return summary or raw_text
