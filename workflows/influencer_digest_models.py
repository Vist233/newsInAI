from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from typing import List, Optional

BAD_CONTENT_MARKERS = (
    "[内容无法获取]",
    "内容无法获取",
    "[content unavailable]",
    "content unavailable",
)

GENERATED_TEXT_ERROR_MARKERS = (
    "provider returned error",
    "rate limit error",
    "temporarily rate-limited",
    "error code: 429",
    "error:",
    "exception:",
    "[总结失败",
    "[summary failed",
)

# Free reasoning models have occasionally returned their scratchpad instead of
# the requested explanation. Keep these markers deliberately specific so
# normal source text is not discarded.
PROMPT_ECHO_MARKERS = (
    "we need to",
    "need to produce",
    "need to write",
    "must follow constraints",
    "must be a single paragraph",
    "must be one paragraph",
    "output requirements",
    "no extra formatting",
    "no extra filler",
    "first sentence:",
    "second sentence:",
    "third sentence:",
    "let's count",
    "now count",
    "count characters",
    "we must not add",
    "the material",
    "chinese explanation",
    "chinese technical news explanation",
    "输入 json",
    "输出要求",
    "一整段连续中文",
    "必须是一整段",
    "禁止补充",
    "提示词",
)

_CJK_RE = re.compile(r"[\u3400-\u9fff]")
_SHORT_FAILURE_PREFIX_RE = re.compile(
    r"^(?:error|exception|failed|failure|timeout|unavailable|rate[- ]?limit)\b"
    r"|^(?:错误|异常|失败|超时|不可用|限流)(?:占位|提示|文本)?\s*[:：-]",
    flags=re.IGNORECASE,
)
_SHORT_FAILURE_BODY_RE = re.compile(
    r"(?:模型|ai|服务|生成|调用|请求|内容).{0,16}"
    r"(?:失败|异常|错误|超时|限流|不可用)"
    r"(?:.{0,16}(?:请|稍后|重试|恢复|暂时))?",
    flags=re.IGNORECASE,
)


INTEREST_KEYWORDS = {
    "agent": [
        "agent",
        "agents",
        "coding agent",
        "computer use",
        "mcp",
        "workflow",
        "automation",
        "autonomous",
        "tool use",
    ],
    "ai_product": [
        "ai product",
        "product",
        "startup",
        "founder",
        "go-to-market",
        "enterprise ai",
        "developer tools",
        "saas",
    ],
    "ai_frontier": [
        "llm",
        "language model",
        "frontier",
        "reasoning",
        "inference",
        "training",
        "open source model",
        "xai",
        "grok",
    ],
    "market": [
        "market",
        "stock",
        "economy",
        "valuation",
        "funding",
        "ipo",
        "revenue",
        "pricing",
        "investment",
    ],
    "security": [
        "security",
        "threat",
        "malware",
        "vulnerability",
        "ransomware",
        "supply chain",
        "attack",
    ],
}


@dataclass
class Source:
    id: str
    name: str
    kind: str
    url: str = ""
    username: str = ""
    rss_path: str = ""
    priority: str = "medium"
    interests: List[str] = field(default_factory=list)
    note: str = ""


@dataclass
class DigestItem:
    kind: str
    source_id: str
    source_name: str
    title: str
    url: str
    published: str
    summary: str
    raw_text: str
    categories: List[str]
    priority: str
    image_url: str = ""
    rank: int = 0


@dataclass
class MovieRecommendation:
    title: str
    year: int
    director: str
    reason: str
    tags: List[str]
    image_url: str = ""


@dataclass
class BookChapterRecommendation:
    title: str
    author: str
    chapter: str
    reason: str
    tags: List[str]


def clean_brief_text(value: Optional[str]) -> str:
    text = str(value or "").strip()
    if not text:
        return ""

    lowered = text.lower()
    if lowered in BAD_CONTENT_MARKERS:
        return ""

    for marker in BAD_CONTENT_MARKERS:
        text = text.replace(marker, "")
    return re.sub(r"\s+", " ", text).strip(" \n\t:-—")


def clean_generated_summary(
    value: Optional[str],
    *,
    require_cjk: bool = False,
    minimum_cjk: int = 0,
    maximum_cjk: int = 0,
) -> str:
    """Return only public-safe model output.

    The generator and the public renderer both use this boundary. That is
    important because an already-persisted bad summary can otherwise bypass
    the generator's validation on the next site build.
    """

    text = clean_brief_text(value)
    if not text:
        return ""

    text = re.sub(r"[*_~#>]", "", text).replace(chr(96), "")
    text = re.sub(r"\s+", " ", text).strip(" \n\t:-—")
    lowered = text.casefold()
    if any(marker in lowered for marker in GENERATED_TEXT_ERROR_MARKERS):
        return ""
    if any(marker in lowered for marker in PROMPT_ECHO_MARKERS):
        return ""
    if _SHORT_FAILURE_PREFIX_RE.search(text) or (
        len(text) <= 140 and _SHORT_FAILURE_BODY_RE.search(text)
    ):
        return ""
    if require_cjk and not _CJK_RE.search(text):
        return ""
    if minimum_cjk and len(_CJK_RE.findall(text)) < minimum_cjk:
        return ""
    if maximum_cjk and len(_CJK_RE.findall(text)) > maximum_cjk:
        return ""
    return text


def strip_title_prefix(text: str, title: str) -> str:
    text = clean_brief_text(text)
    title = clean_brief_text(title)
    if not text or not title:
        return text
    if text == title:
        return ""
    if text.startswith(title):
        return text[len(title) :].strip(" \n\t:-—")
    return text


def sanitize_digest_item(item: DigestItem) -> DigestItem:
    summary = clean_brief_text(item.summary)
    raw_text = clean_brief_text(item.raw_text)

    # News, Trending, and arXiv summaries are generated Chinese copy. The
    # smol.ai row uses source-provided English copy and is intentionally left
    # outside this check.
    if item.kind in {"paper", "github_trending"} or (
        item.kind == "hacker_news" and item.source_id != "smol_ai"
    ):
        summary = clean_generated_summary(
            summary,
            require_cjk=True,
            minimum_cjk=60,
            maximum_cjk=220,
        )

    if item.kind in {"youtube", "bilibili"} and not summary:
        raw_text = strip_title_prefix(raw_text, item.title)

    return replace(item, summary=summary, raw_text=raw_text)
