#!/usr/bin/env python3
"""Send a Feishu/Lark interactive card linking to the latest AI Industry Daily page.

Required env:
  FEISHU_WEBHOOK

Optional env:
  FEISHU_SECRET   signing secret if your bot uses signature verification
  REPORT_URL      default: https://dyn-lisa.github.io/ai-industry-daily/
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "data" / "latest_report.json"


def truncate(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def load_report() -> dict[str, Any]:
    if not REPORT_PATH.exists():
        return {
            "dateCN": "今日",
            "dateEN": "Today",
            "summaryCN": "今日AI行业重点新闻已整理完成。",
            "summaryEN": "Today's AI industry briefing is ready.",
            "items": [],
        }
    return json.loads(REPORT_PATH.read_text(encoding="utf-8"))


def sign_payload_if_needed(payload: dict[str, Any]) -> dict[str, Any]:
    secret = os.environ.get("FEISHU_SECRET", "").strip()
    if not secret:
        return payload
    timestamp = str(int(time.time()))
    string_to_sign = f"{timestamp}\n{secret}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), string_to_sign, hashlib.sha256).digest()
    payload = dict(payload)
    payload["timestamp"] = timestamp
    payload["sign"] = base64.b64encode(digest).decode("utf-8")
    return payload


def build_card(report: dict[str, Any], report_url: str) -> dict[str, Any]:
    items = report.get("items", [])[:3]
    if items:
        top_lines_cn = "\n".join(
            [f"{item.get('rank', idx + 1)}. {item.get('titleCN', '')} — {item.get('source', '')}" for idx, item in enumerate(items)]
        )
        top_lines_en = "\n".join(
            [f"{item.get('rank', idx + 1)}. {item.get('titleEN', '')}" for idx, item in enumerate(items)]
        )
    else:
        top_lines_cn = "今日Top 3新闻请点击完整日报查看。"
        top_lines_en = "Open the full report to view today's Top 3 stories."

    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "title": {"tag": "plain_text", "content": "🤖 AI日报已更新 / AI Industry Daily Updated"},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": (
                            f"**{report.get('dateCN', '')} / {report.get('dateEN', '')}**\n"
                            "完整双语AI行业日报已生成，点击下方按钮查看网页版本。"
                        ),
                    },
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**摘要 / Summary**\n【CN】{truncate(report.get('summaryCN', ''), 260)}\n\n【EN】{truncate(report.get('summaryEN', ''), 420)}",
                    },
                },
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**Top 3 今日重点**\n{top_lines_cn}\n\n**Top 3 Highlights**\n{top_lines_en}",
                    },
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "查看完整日报 / Read Full Report"},
                            "type": "primary",
                            "url": report_url,
                        }
                    ],
                },
            ],
        },
    }


def send_card(webhook: str, payload: dict[str, Any]) -> None:
    data = json.dumps(sign_payload_if_needed(payload), ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        webhook,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            body = response.read().decode("utf-8", errors="replace")
            print(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Feishu HTTP {exc.code}: {body}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Failed to send Feishu card: {exc}") from exc


def main() -> None:
    webhook = os.environ.get("FEISHU_WEBHOOK", "").strip()
    if not webhook.startswith("https://"):
        raise RuntimeError("FEISHU_WEBHOOK is missing or invalid. It must start with https://")
    report_url = os.environ.get("REPORT_URL", "https://dyn-lisa.github.io/ai-industry-daily/").strip()
    report = load_report()
    payload = build_card(report, report_url)
    send_card(webhook, payload)


if __name__ == "__main__":
    main()
