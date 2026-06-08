#!/usr/bin/env python3
"""Send a Feishu/Lark interactive card for the AI Industry Daily report.

Required environment variable:
  FEISHU_WEBHOOK  The custom bot webhook URL from Feishu.

Optional environment variables:
  REPORT_URL      The public URL of the full HTML report.
  TIMEZONE        IANA timezone name. Default: Asia/Tokyo.
  TOP_ITEMS       A pipe-separated list of top items to show in the card.
                  Example: "OpenAI updates Codex|NVIDIA launches agent tools|AI safety letter"
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime
from zoneinfo import ZoneInfo


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None or value.strip() == "":
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


def build_card(report_url: str, timezone_name: str, top_items: list[str]) -> dict:
    now = datetime.now(ZoneInfo(timezone_name))
    cn_date = f"{now.month}月{now.day}日"
    en_date = now.strftime("%B %-d") if sys.platform != "win32" else now.strftime("%B %#d")

    top_items_md = "\n".join(f"{idx}. {item}" for idx, item in enumerate(top_items, start=1))

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "blue",
                "title": {
                    "tag": "plain_text",
                    "content": f"🤖 AI日报已更新 / AI Industry Daily Updated · {cn_date}",
                },
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            "**AI日报 / AI Industry Daily**\n"
                            f"今日（{cn_date} / {en_date}）AI行业重点新闻已整理完成。"
                            "点击下方按钮查看完整双语HTML日报。\n\n"
                            "The full bilingual AI industry report is ready. "
                            "Tap the button below to read the HTML version."
                        ),
                    },
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**Top 3 今日重点 / Highlights:**\n{top_items_md}",
                    },
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {
                                "tag": "plain_text",
                                "content": "查看完整日报 / Read Full Report",
                            },
                            "type": "primary",
                            "url": report_url,
                        }
                    ],
                },
            ],
        },
    }


def send_card(webhook: str, payload: dict) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            text = response.read().decode("utf-8")
            print(text)
            if response.status >= 400:
                raise RuntimeError(f"Feishu webhook returned HTTP {response.status}: {text}")
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                return
            if data.get("code", 0) != 0:
                raise RuntimeError(f"Feishu webhook error: {text}")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to send Feishu card: {exc}") from exc


def main() -> None:
    webhook = env("FEISHU_WEBHOOK")
    report_url = env("REPORT_URL", "https://dyn-lisa.github.io/ai-industry-daily/")
    timezone_name = env("TIMEZONE", "Asia/Tokyo")
    raw_top_items = env(
        "TOP_ITEMS",
        "AI governance and safety updates|AI infrastructure and capital expenditure trends|Agentic AI product and enterprise deployment news",
    )
    top_items = [item.strip() for item in raw_top_items.split("|") if item.strip()]
    if not top_items:
        top_items = ["AI industry daily report is ready"]

    payload = build_card(report_url, timezone_name, top_items[:3])
    send_card(webhook, payload)


if __name__ == "__main__":
    main()
