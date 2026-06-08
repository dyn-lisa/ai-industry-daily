#!/usr/bin/env python3
"""Replace the `const reportData = {...};` block in index.html.

The HTML template renders the page entirely from this JavaScript object. This
script updates only that data object and leaves styling / layout untouched.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


class ReportDataBlockError(RuntimeError):
    pass


def find_report_data_block(html: str) -> tuple[int, int]:
    """Return [start, end) indices for `const reportData = {...};`.

    This scanner understands JavaScript strings enough to avoid stopping on a
    brace inside a quoted title or abstract.
    """

    marker = "const reportData ="
    start = html.find(marker)
    if start < 0:
        raise ReportDataBlockError("Could not find `const reportData =` in HTML.")

    brace_start = html.find("{", start)
    if brace_start < 0:
        raise ReportDataBlockError("Could not find opening `{` for reportData.")

    depth = 0
    in_string: str | None = None
    escaped = False
    i = brace_start
    while i < len(html):
        ch = html[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == in_string:
                in_string = None
        else:
            if ch in {"'", '"', "`"}:
                in_string = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    semicolon = html.find(";", i)
                    if semicolon < 0:
                        raise ReportDataBlockError("Could not find semicolon after reportData object.")
                    return start, semicolon + 1
        i += 1

    raise ReportDataBlockError("Could not find matching closing `}` for reportData.")


def replace_report_data(html: str, report: dict) -> str:
    start, end = find_report_data_block(html)
    data_json = json.dumps(report, ensure_ascii=False, indent=6)
    replacement = f"const reportData = {data_json};"
    return html[:start] + replacement + html[end:]


def update_html_file(html_path: Path, report_path: Path, output_path: Path | None = None) -> None:
    report = json.loads(report_path.read_text(encoding="utf-8"))
    html = html_path.read_text(encoding="utf-8")
    updated = replace_report_data(html, report)
    target = output_path or html_path
    target.write_text(updated, encoding="utf-8")
    print(f"Updated {target} with report data from {report_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Update index.html with latest reportData JSON.")
    parser.add_argument("report_json", type=Path, help="Path to generated report JSON")
    parser.add_argument("html", type=Path, nargs="?", default=Path("index.html"), help="Path to index.html")
    parser.add_argument("--output", type=Path, default=None, help="Optional output HTML path")
    args = parser.parse_args()
    update_html_file(args.html, args.report_json, args.output)


if __name__ == "__main__":
    main()
