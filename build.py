#!/usr/bin/env python3
"""把 content/YYYY-MM-DD.json 渲染成站点（复用主仓库渲染器，保证版式一致）。

用法：python3 build.py [YYYY-MM-DD]
产物：site/index.html、site/reports/<date>.html、site/rss.xml、site/latest.json
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from workflows.influencer_digest_models import (  # noqa: E402
    BookChapterRecommendation,
    DigestItem,
    MovieRecommendation,
)
from workflows.influencer_digest_render import SiteRenderer  # noqa: E402

ROOT = Path(__file__).resolve().parent


def main() -> int:
    day = sys.argv[1] if len(sys.argv) > 1 else datetime.now().strftime("%Y-%m-%d")
    src = ROOT / "content" / f"{day}.json"
    if not src.exists():
        print(f"缺少内容文件: {src}")
        return 1
    payload = json.loads(src.read_text(encoding="utf-8"))

    items = []
    for raw in payload["items"]:
        data = {k: v for k, v in raw.items() if k in DigestItem.__dataclass_fields__}
        data.setdefault("categories", [])
        data.setdefault("priority", "normal")
        data.setdefault("raw_text", "")
        data.setdefault("summary", "")
        items.append(DigestItem(**data))

    movie_raw = payload["movie"]
    movie = MovieRecommendation(
        title=movie_raw["title"],
        year=int(movie_raw["year"]),
        director=movie_raw["director"],
        reason=movie_raw["reason"],
        tags=movie_raw.get("tags") or [],
        image_url=movie_raw.get("image_url", ""),
    )
    book = None
    if payload.get("book"):
        b = payload["book"]
        book = BookChapterRecommendation(
            title=b["title"],
            author=b["author"],
            chapter=b.get("chapter", ""),
            reason=b["reason"],
            tags=b.get("tags") or [],
        )

    renderer = SiteRenderer(ROOT / "site")
    paths = renderer.render(
        items,
        payload["summary"],
        movie,
        book,
        issue_monitor=payload.get("issue_monitor"),
    )
    print("index:", paths["index"])
    print("items:", len(items), "| kinds:", sorted({i.kind for i in items}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
