"""RSS and scoring configuration for the AI Industry Daily generator.

Edit this file when you want to add/remove sources or adjust scoring keywords.
The generator uses Google News RSS plus a small set of AI/tech RSS feeds.
"""

from __future__ import annotations

from urllib.parse import quote_plus


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


GOOGLE_NEWS_FEEDS = [
    google_news_rss_url(query, hl, gl, ceid)
    for query in GOOGLE_NEWS_QUERIES
    for hl, gl, ceid in GOOGLE_NEWS_LOCALES
]

# These feeds are intentionally best-effort. If one feed breaks, the generator
# logs a warning and continues with the rest.
DIRECT_RSS_FEEDS = [
    "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    "https://techcrunch.com/category/artificial-intelligence/feed/",
    "https://venturebeat.com/category/ai/feed/",
    "https://www.artificialintelligence-news.com/feed/",
    "https://blogs.nvidia.com/blog/category/ai/feed/",
    "https://www.microsoft.com/en-us/ai/blog/feed/",
    "https://openai.com/news/rss.xml",
]

RSS_FEEDS = GOOGLE_NEWS_FEEDS + DIRECT_RSS_FEEDS

# Source weights are deliberately modest. Recency and content relevance still matter.
SOURCE_WEIGHTS = {
    "Reuters": 18,
    "Associated Press": 16,
    "AP News": 16,
    "Bloomberg": 16,
    "Wall Street Journal": 16,
    "Financial Times": 16,
    "The Information": 14,
    "The Verge": 13,
    "TechCrunch": 13,
    "MIT Technology Review": 13,
    "CNBC": 12,
    "Wired": 12,
    "Business Insider": 10,
    "VentureBeat": 9,
    "NVIDIA Blog": 8,
    "OpenAI": 8,
    "Google Blog": 8,
    "Microsoft": 8,
}

KEYWORD_WEIGHTS = {
    # companies / labs
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
    # themes
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

# Avoid entertainment gossip and non-industry fluff unless it has obvious legal/labor/platform implications.
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
