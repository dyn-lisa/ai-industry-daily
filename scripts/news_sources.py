"""RSS source and scoring configuration for the AI Industry Daily generator.

This module is intentionally lightweight and dependency-free so it can run in
GitHub Actions without installing packages. Edit this file when you want to add
or remove news sources, or tune ranking keywords.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote_plus


@dataclass(frozen=True)
class Feed:
    """A single RSS/Atom feed definition."""

    name: str
    url: str
    weight: float = 1.0


GOOGLE_NEWS_LOCALES = [
    ("en-US", "US", "US:en"),
    ("zh-CN", "CN", "CN:zh-Hans"),
]

GOOGLE_NEWS_QUERIES = [
    "AI industry when:1d",
    "artificial intelligence OpenAI Anthropic Google DeepMind Microsoft Nvidia when:1d",
    "generative AI enterprise agents chips data centers regulation when:1d",
    "AI model release benchmark safety copyright deepfake when:1d",
    "人工智能 行业 大模型 芯片 监管 when:1d",
    "OpenAI Anthropic DeepMind Nvidia 微软 人工智能 when:1d",
]


def google_news_rss_url(query: str, hl: str, gl: str, ceid: str) -> str:
    return (
        "https://news.google.com/rss/search?"
        f"q={quote_plus(query)}&hl={quote_plus(hl)}&gl={quote_plus(gl)}&ceid={quote_plus(ceid)}"
    )


GOOGLE_NEWS_FEEDS: list[Feed] = [
    Feed(
        name=f"Google News: {query[:48]}",
        url=google_news_rss_url(query, hl, gl, ceid),
        weight=2.0,
    )
    for query in GOOGLE_NEWS_QUERIES
    for hl, gl, ceid in GOOGLE_NEWS_LOCALES
]

# These direct feeds are best-effort. If one breaks, generate_daily_report.py
# logs a warning and continues with the others.
DIRECT_RSS_FEEDS: list[Feed] = [
    Feed("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", 2.4),
    Feed("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/", 2.3),
    Feed("VentureBeat AI", "https://venturebeat.com/category/ai/feed/", 2.0),
    Feed("Artificial Intelligence News", "https://www.artificialintelligence-news.com/feed/", 1.7),
    Feed("NVIDIA Blog", "https://blogs.nvidia.com/blog/category/ai/feed/", 1.8),
    Feed("Microsoft AI Blog", "https://www.microsoft.com/en-us/ai/blog/feed/", 1.8),
    Feed("OpenAI News", "https://openai.com/news/rss.xml", 1.9),
]

# The generator imports DEFAULT_FEEDS directly.
DEFAULT_FEEDS: list[Feed] = GOOGLE_NEWS_FEEDS + DIRECT_RSS_FEEDS

# Optional aliases kept for compatibility / easier debugging.
RSS_FEEDS: list[str] = [feed.url for feed in DEFAULT_FEEDS]

# Source weights are deliberately modest. Recency, keyword relevance, and
# multi-source mentions still matter.
SOURCE_WEIGHTS: dict[str, float] = {
    "reuters": 18,
    "associated press": 16,
    "ap news": 16,
    "bloomberg": 16,
    "wall street journal": 16,
    "wsj": 16,
    "financial times": 16,
    "the information": 14,
    "the verge": 13,
    "techcrunch": 13,
    "mit technology review": 13,
    "cnbc": 12,
    "wired": 12,
    "business insider": 10,
    "venturebeat": 9,
    "nvidia": 8,
    "openai": 8,
    "google": 8,
    "deepmind": 8,
    "microsoft": 8,
}

KEYWORD_WEIGHTS: dict[str, float] = {
    # Companies / labs
    "openai": 12,
    "anthropic": 12,
    "google": 9,
    "deepmind": 12,
    "microsoft": 10,
    "nvidia": 12,
    "meta": 8,
    "amazon": 7,
    "aws": 7,
    "apple": 7,
    "xai": 7,
    "mistral": 7,
    "perplexity": 6,
    "cohere": 5,
    "hugging face": 5,
    "deepseek": 8,
    "alibaba": 6,
    "tencent": 6,
    "baidu": 6,
    "字节": 6,
    "阿里": 6,
    "腾讯": 6,
    "百度": 6,
    # Themes
    "ai agent": 10,
    "agents": 8,
    "agentic": 8,
    "artificial intelligence": 9,
    "generative ai": 9,
    "foundation model": 8,
    "large language model": 8,
    "llm": 8,
    "multimodal": 7,
    "reasoning model": 7,
    "model release": 7,
    "open source": 7,
    "benchmark": 5,
    "gpu": 8,
    "chip": 7,
    "semiconductor": 7,
    "data center": 9,
    "compute": 7,
    "infrastructure": 7,
    "cloud": 6,
    "enterprise ai": 9,
    "regulation": 9,
    "safety": 9,
    "copyright": 8,
    "lawsuit": 7,
    "deepfake": 7,
    "privacy": 6,
    "security": 6,
    "funding": 6,
    "valuation": 6,
    "acquisition": 6,
    "partnership": 5,
    "人工智能": 9,
    "大模型": 9,
    "智能体": 9,
    "算力": 8,
    "芯片": 8,
    "监管": 8,
    "开源": 7,
    "融资": 6,
}

# Avoid entertainment gossip and non-industry fluff unless it has obvious
# legal/labor/platform implications.
NEGATIVE_KEYWORDS = [
    "celebrity",
    "gossip",
    "dating",
    "movie trailer",
    "box office",
    "fan art",
    "horoscope",
    "astrology",
    "game cheat",
    "memecoin",
    "娱乐八卦",
    "明星恋情",
]

REQUIRED_AI_HINTS = [
    "ai",
    "artificial intelligence",
    "generative",
    "llm",
    "model",
    "openai",
    "anthropic",
    "deepmind",
    "nvidia",
    "人工智能",
    "大模型",
    "智能体",
]

TOKEN_RE = re.compile(r"[a-z0-9]+|[\u4e00-\u9fff]+", re.IGNORECASE)


def normalize_text(value: str | None) -> str:
    return (value or "").casefold()


def tokenize(text: str) -> set[str]:
    """Tokenize English words/numbers and Chinese character runs for deduping."""

    return {token.casefold() for token in TOKEN_RE.findall(text or "") if len(token) >= 2}


def has_excluded_topic(text: str) -> bool:
    """Return True if a story should be excluded before scoring."""

    lowered = normalize_text(text)
    if not lowered.strip():
        return True
    if any(keyword.casefold() in lowered for keyword in NEGATIVE_KEYWORDS):
        return True
    # Keep the candidate pool AI-focused. Google News can occasionally return
    # stories where "AI" appears in unrelated names or low-signal contexts.
    if not any(hint.casefold() in lowered for hint in REQUIRED_AI_HINTS):
        return True
    return False


def source_weight(source: str) -> float:
    """Return extra ranking weight for trusted/high-signal publishers."""

    lowered = normalize_text(source)
    for name, weight in SOURCE_WEIGHTS.items():
        if name in lowered:
            return float(weight)
    return 0.0


def keyword_score(text: str) -> float:
    """Return weighted keyword score for AI-industry relevance."""

    lowered = normalize_text(text)
    total = 0.0
    for keyword, weight in KEYWORD_WEIGHTS.items():
        if keyword.casefold() in lowered:
            total += float(weight)
    return total
