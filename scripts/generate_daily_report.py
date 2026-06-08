#!/usr/bin/env python3
"""Generate a bilingual AI Industry Daily report and update index.html.

Pipeline:
1. Fetch RSS / Google News RSS candidates from configured sources.
2. Filter, deduplicate, and score candidate AI industry news.
3. Ask OpenAI to select and summarize the top 10 in Chinese + English.
4. Write data/latest_report.json, data/reports/report_YYYYMMDD.json, and update index.html.

Environment variables:
  OPENAI_API_KEY       Required.
  OPENAI_MODEL         Optional. Default: gpt-4.1-mini
  OPENAI_BASE_URL      Optional. Default: https://api.openai.com/v1
  TIMEZONE             Optional. Default: Asia/Singapore
  MAX_CANDIDATES       Optional. Default: 60
  REPORT_EDITOR        Optional. Default: News Intelligence Assistant
  EXTRA_RSS_FEEDS      Optional. Newline-separated "Name|URL|Weight" custom feeds.
"""

from __future__ import annotations

import argparse
import email.utils
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from news_sources import (
    DEFAULT_FEEDS,
    Feed,
    has_excluded_topic,
    keyword_score,
    source_weight,
    tokenize,
)
from update_html import update_html_file

USER_AGENT = "AIIndustryDailyBot/1.0 (+https://dyn-lisa.github.io/ai-industry-daily/)"


@dataclass
class NewsItem:
    title: str
    url: str
    source: str
    feed_name: str
    published: str = ""
    published_ts: float = 0.0
    summary: str = ""
    score: float = 0.0
    mentions: int = 1
    matched_sources: list[str] = field(default_factory=list)

    def compact(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "url": self.url,
            "source": self.source,
            "feed": self.feed_name,
            "published": self.published,
            "summary": self.summary[:800],
            "score": round(self.score, 2),
            "mentions": self.mentions,
            "matched_sources": self.matched_sources[:6],
        }


TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")


def env(name: str, default: str | None = None, *, required: bool = False) -> str:
    value = os.environ.get(name, default)
    if required and (value is None or value.strip() == ""):
        raise RuntimeError(f"Missing required environment variable: {name}")
    return (value or "").strip()


def strip_html(value: str | None) -> str:
    value = html.unescape(value or "")
    value = TAG_RE.sub(" ", value)
    return WHITESPACE_RE.sub(" ", value).strip()


def parse_date(value: str | None) -> tuple[str, float]:
    if not value:
        return "", 0.0
    text = value.strip()
    try:
        dt = email.utils.parsedate_to_datetime(text)
        if dt is None:
            return text, 0.0
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat(), dt.timestamp()
    except Exception:
        # Best-effort ISO parser fallback.
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.isoformat(), dt.timestamp()
        except Exception:
            return text, 0.0


def fetch_url(url: str, *, timeout: int = 25) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def child_text(element: ET.Element, names: list[str]) -> str:
    for name in names:
        found = element.find(name)
        if found is not None and found.text:
            return found.text.strip()
    # Namespace-agnostic fallback.
    wanted = {n.split("}")[-1].lower() for n in names}
    for child in list(element):
        local = child.tag.split("}")[-1].lower()
        if local in wanted and child.text:
            return child.text.strip()
    return ""


def atom_link(element: ET.Element) -> str:
    # RSS: <link>...</link>
    direct = child_text(element, ["link"])
    if direct:
        return direct
    # Atom: <link href="..." />
    for child in list(element):
        local = child.tag.split("}")[-1].lower()
        if local == "link" and child.attrib.get("href"):
            return child.attrib["href"].strip()
    return ""


def source_from_item(element: ET.Element, feed_name: str) -> str:
    for child in list(element):
        local = child.tag.split("}")[-1].lower()
        if local == "source" and child.text:
            return child.text.strip()
    return feed_name


def parse_feed(xml_bytes: bytes, feed: Feed) -> list[NewsItem]:
    root = ET.fromstring(xml_bytes)
    # RSS uses channel/item; Atom uses entry.
    raw_items = root.findall(".//item")
    if not raw_items:
        raw_items = [el for el in root.iter() if el.tag.split("}")[-1].lower() == "entry"]

    parsed: list[NewsItem] = []
    for item in raw_items:
        title = strip_html(child_text(item, ["title"]))
        url = atom_link(item)
        summary = strip_html(child_text(item, ["description", "summary", "content", "content:encoded"]))
        source = strip_html(source_from_item(item, feed.name)) or feed.name
        pub_raw = child_text(item, ["pubDate", "published", "updated", "dc:date"])
        published, published_ts = parse_date(pub_raw)

        if not title or not url:
            continue
        text_for_filter = f"{title} {summary} {source}"
        if has_excluded_topic(text_for_filter):
            continue
        parsed.append(
            NewsItem(
                title=title,
                url=url,
                source=source,
                feed_name=feed.name,
                published=published,
                published_ts=published_ts,
                summary=summary,
                matched_sources=[source],
                score=feed.weight,
            )
        )
    return parsed


def load_extra_feeds() -> list[Feed]:
    raw = env("EXTRA_RSS_FEEDS")
    feeds: list[Feed] = []
    if not raw:
        return feeds
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 2:
            print(f"Skipping invalid EXTRA_RSS_FEEDS line: {line}")
            continue
        name, url = parts[0], parts[1]
        try:
            weight = float(parts[2]) if len(parts) >= 3 and parts[2] else 1.8
        except ValueError:
            weight = 1.8
        feeds.append(Feed(name, url, weight))
    return feeds


def fetch_candidates() -> list[NewsItem]:
    feeds = [*DEFAULT_FEEDS, *load_extra_feeds()]
    candidates: list[NewsItem] = []
    for feed in feeds:
        try:
            xml_bytes = fetch_url(feed.url)
            items = parse_feed(xml_bytes, feed)
            print(f"Fetched {len(items):>3} items from {feed.name}")
            candidates.extend(items)
        except Exception as exc:  # noqa: BLE001 - feed failures should not kill the run
            print(f"Warning: failed to fetch {feed.name}: {exc}")
    return candidates


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def recency_score(item: NewsItem, now_ts: float) -> float:
    if not item.published_ts:
        return 0.8
    age_hours = max(0.0, (now_ts - item.published_ts) / 3600)
    if age_hours <= 12:
        return 4.0
    if age_hours <= 24:
        return 3.2
    if age_hours <= 48:
        return 1.6
    return 0.4


def score_item(item: NewsItem, now_ts: float) -> float:
    text = f"{item.title} {item.summary} {item.source}"
    return (
        item.score
        + source_weight(item.source)
        + keyword_score(text)
        + recency_score(item, now_ts)
        + min(item.mentions, 6) * 1.15
    )


def dedupe_and_score(items: list[NewsItem], timezone_name: str) -> list[NewsItem]:
    now_ts = datetime.now(ZoneInfo(timezone_name)).timestamp()
    clusters: list[tuple[set[str], NewsItem]] = []

    # Process stronger items first so the retained representative is usually the better source/link.
    for item in items:
        item.score = score_item(item, now_ts)
    for item in sorted(items, key=lambda x: x.score, reverse=True):
        tokens = tokenize(item.title)
        matched_idx: int | None = None
        for idx, (existing_tokens, existing) in enumerate(clusters):
            if item.url == existing.url or jaccard(tokens, existing_tokens) >= 0.62:
                matched_idx = idx
                break
        if matched_idx is None:
            clusters.append((tokens, item))
        else:
            existing_tokens, existing = clusters[matched_idx]
            existing.mentions += 1
            if item.source not in existing.matched_sources:
                existing.matched_sources.append(item.source)
            # Prefer a non-Google News publisher URL if scores are similar.
            if ("news.google.com" in existing.url and "news.google.com" not in item.url) or item.score > existing.score + 1.0:
                item.mentions = existing.mentions
                item.matched_sources = existing.matched_sources
                clusters[matched_idx] = (existing_tokens | tokens, item)
            else:
                clusters[matched_idx] = (existing_tokens | tokens, existing)

    deduped = [item for _, item in clusters]
    for item in deduped:
        item.score = score_item(item, now_ts)
    return sorted(deduped, key=lambda x: x.score, reverse=True)


def date_strings(timezone_name: str, forced_date: str | None = None) -> tuple[datetime, str, str, str]:
    tz = ZoneInfo(timezone_name)
    if forced_date:
        base = datetime.fromisoformat(forced_date).replace(tzinfo=tz)
    else:
        base = datetime.now(tz)
    date_cn = f"{base.year}年{base.month}月{base.day}日"
    date_en = base.strftime("%B %-d, %Y") if sys.platform != "win32" else base.strftime("%B %#d, %Y")
    compact = base.strftime("%Y%m%d")
    return base, date_cn, date_en, compact


def report_schema() -> dict[str, Any]:
    signal_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["labelCN", "labelEN", "textCN", "textEN"],
        "properties": {
            "labelCN": {"type": "string"},
            "labelEN": {"type": "string"},
            "textCN": {"type": "string"},
            "textEN": {"type": "string"},
        },
    }
    item_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["rank", "titleCN", "titleEN", "url", "abstractCN", "abstractEN", "source", "tags"],
        "properties": {
            "rank": {"type": "integer", "minimum": 1, "maximum": 10},
            "titleCN": {"type": "string"},
            "titleEN": {"type": "string"},
            "url": {"type": "string"},
            "abstractCN": {"type": "string"},
            "abstractEN": {"type": "string"},
            "source": {"type": "string"},
            "tags": {"type": "array", "minItems": 1, "maxItems": 4, "items": {"type": "string"}},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "dateCN",
            "dateEN",
            "issueNo",
            "editor",
            "titleCN",
            "titleEN",
            "subtitleCN",
            "subtitleEN",
            "summaryCN",
            "summaryEN",
            "signals",
            "items",
        ],
        "properties": {
            "dateCN": {"type": "string"},
            "dateEN": {"type": "string"},
            "issueNo": {"type": "string"},
            "editor": {"type": "string"},
            "titleCN": {"type": "string"},
            "titleEN": {"type": "string"},
            "subtitleCN": {"type": "string"},
            "subtitleEN": {"type": "string"},
            "summaryCN": {"type": "string"},
            "summaryEN": {"type": "string"},
            "signals": {"type": "array", "minItems": 3, "maxItems": 3, "items": signal_schema},
            "items": {"type": "array", "minItems": 10, "maxItems": 10, "items": item_schema},
        },
    }


def build_prompt(candidates: list[NewsItem], timezone_name: str, forced_date: str | None) -> tuple[str, str]:
    _, date_cn, date_en, compact = date_strings(timezone_name, forced_date)
    candidate_payload = [item.compact() for item in candidates]
    system = (
        "You are a professional News Intelligence Assistant specializing in the AI industry. "
        "Select the most noteworthy, high-attention, industry-relevant AI news items from the candidate list. "
        "Do not include entertainment gossip, clickbait, horoscope, celebrity, or low-signal stories. "
        "Do not invent facts, sources, URLs, or dates. Use only candidate URLs. "
        "Write clear, natural bilingual Chinese and English."
    )
    user = f"""
Today's target date is {date_en} / {date_cn}. Timezone: {timezone_name}.

Task:
Create a bilingual AI industry daily report in exactly this structure:
- Around 100 English words for summaryEN.
- A natural Chinese counterpart for summaryCN.
- Exactly 3 key signals.
- Exactly 10 news items sorted by importance.
- Each news item must have Chinese and English titles, the original URL, Chinese and English abstract, source, and tags.

Ranking guidance:
Prioritize items with high industry impact, wide discussion, leading companies/labs, policy/regulatory consequences, capital/compute implications, enterprise adoption, major model/product launches, lawsuits, labor/copyright disputes, and AI safety/governance.

Candidate stories, already roughly scored and deduplicated:
{json.dumps(candidate_payload, ensure_ascii=False, indent=2)}

Return only valid JSON matching the requested schema. No markdown.
""".strip()
    return system, user


def openai_responses_request(system: str, user: str) -> dict[str, Any]:
    api_key = env("OPENAI_API_KEY", required=True)
    model = env("OPENAI_MODEL", "gpt-4.1-mini")
    base_url = env("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
    url = f"{base_url}/responses"
    payload = {
        "model": model,
        "input": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "ai_daily_report",
                "strict": True,
                "schema": report_schema(),
            }
        },
        "temperature": 0.2,
        "max_output_tokens": 9000,
    }

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            text = response.read().decode("utf-8")
            if response.status >= 400:
                raise RuntimeError(f"OpenAI API returned HTTP {response.status}: {text}")
            return json.loads(text)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI API HTTPError {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OpenAI API request failed: {exc}") from exc


def extract_response_text(data: dict[str, Any]) -> str:
    if isinstance(data.get("output_text"), str) and data["output_text"].strip():
        return data["output_text"].strip()

    pieces: list[str] = []
    for output in data.get("output", []) or []:
        for content in output.get("content", []) or []:
            if isinstance(content, dict):
                if isinstance(content.get("text"), str):
                    pieces.append(content["text"])
                elif isinstance(content.get("output_text"), str):
                    pieces.append(content["output_text"])
    text = "\n".join(pieces).strip()
    if not text:
        raise RuntimeError(f"Could not extract text from OpenAI response: {json.dumps(data)[:1000]}")
    return text


def parse_json_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            return json.loads(cleaned[start : end + 1])
        raise


def normalize_report(report: dict[str, Any], timezone_name: str, forced_date: str | None, candidates: list[NewsItem]) -> dict[str, Any]:
    _, date_cn, date_en, compact = date_strings(timezone_name, forced_date)
    report["dateCN"] = date_cn
    report["dateEN"] = date_en
    report["issueNo"] = f"AI-Daily-{compact}"
    report["editor"] = env("REPORT_EDITOR", "News Intelligence Assistant")
    report["titleCN"] = report.get("titleCN") or "今日AI行业新闻"
    report["titleEN"] = report.get("titleEN") or "Today's AI Industry News"
    report["subtitleCN"] = report.get("subtitleCN") or "聚焦AI行业当日高热度、高讨论度、高影响力事件。"
    report["subtitleEN"] = report.get("subtitleEN") or "A bilingual briefing on the most discussed and consequential AI industry stories of the day."

    candidate_urls = {item.url for item in candidates}
    normalized_items: list[dict[str, Any]] = []
    for rank, item in enumerate(report.get("items", [])[:10], start=1):
        item = dict(item)
        item["rank"] = rank
        # If the model somehow returns a URL not from candidates, keep it but warn.
        if item.get("url") not in candidate_urls:
            print(f"Warning: item URL was not found in candidates: {item.get('url')}")
        tags = item.get("tags") or ["AI Industry"]
        if isinstance(tags, str):
            tags = [tags]
        item["tags"] = [str(tag)[:40] for tag in tags[:4] if str(tag).strip()] or ["AI Industry"]
        normalized_items.append(item)

    if len(normalized_items) < 10:
        raise RuntimeError(f"OpenAI returned only {len(normalized_items)} items; expected 10.")
    report["items"] = normalized_items
    return report


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate and publish AI Industry Daily report data.")
    parser.add_argument("--html", type=Path, default=Path("index.html"), help="Path to index.html")
    parser.add_argument("--timezone", default=env("TIMEZONE", "Asia/Singapore"), help="IANA timezone")
    parser.add_argument("--date", default=env("REPORT_DATE", ""), help="Optional forced date YYYY-MM-DD")
    parser.add_argument("--max-candidates", type=int, default=int(env("MAX_CANDIDATES", "60")))
    parser.add_argument("--dry-run", action="store_true", help="Generate JSON but do not update HTML")
    args = parser.parse_args()

    forced_date = args.date or None
    _, date_cn, date_en, compact = date_strings(args.timezone, forced_date)
    print(f"Generating AI Industry Daily for {date_en} / {date_cn}")

    raw_candidates = fetch_candidates()
    if not raw_candidates:
        raise RuntimeError("No news candidates fetched. Check network access or RSS feeds.")
    ranked = dedupe_and_score(raw_candidates, args.timezone)
    selected = ranked[: args.max_candidates]
    print(f"Selected {len(selected)} candidate stories after scoring/deduping")

    write_json(Path(f"data/candidates/candidates_{compact}.json"), [item.compact() for item in selected])

    if len(selected) < 10:
        raise RuntimeError(f"Only {len(selected)} candidate stories found; need at least 10.")

    system, user = build_prompt(selected, args.timezone, forced_date)
    response = openai_responses_request(system, user)
    text = extract_response_text(response)
    report = parse_json_text(text)
    report = normalize_report(report, args.timezone, forced_date, selected)

    latest_path = Path("data/latest_report.json")
    dated_path = Path(f"data/reports/report_{compact}.json")
    write_json(latest_path, report)
    write_json(dated_path, report)

    if not args.dry_run:
        if not args.html.exists():
            raise RuntimeError(f"HTML file does not exist: {args.html}")
        update_html_file(args.html, latest_path)
    else:
        print("Dry run enabled: index.html was not updated.")


if __name__ == "__main__":
    main()
