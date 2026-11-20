"""Send the daily scan report to Telegram.

Tries a Rich Message (sendRichMessage) built from scan_report_telegram.json and
falls back to a plain sendMessage with the markdown report. Stdlib only. The bot
token is never printed.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

RICH_PAYLOAD_PATH = Path("scan_report_telegram.json")
REPORT_PATH = Path("scan_report.md")

# Bot API "Rich Message Limits"
MAX_RICH_CHARS = 32768
MAX_RICH_BLOCKS = 500
MAX_TABLE_COLUMNS = 20

MAX_PLAIN_CHARS = 3500
TRUNCATION_SUFFIX = "\n\n(Report truncated to fit Telegram message limits.)"


def _scrub(text: object, token: str) -> str:
    out = str(text)
    return out.replace(token, "***") if token else out


def _post(url: str, data: bytes, headers: dict[str, str], token: str) -> tuple[bool, str]:
    """POST and return (ok, detail). detail is "message_id=N" on success (the response body is
    never returned, it contains chat details), or an error description."""
    req = Request(url, data=data, headers=headers, method="POST")
    try:
        with urlopen(req, timeout=30) as response:
            body = response.read().decode("utf-8")
    except HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
            description = json.loads(raw).get("description", raw)
        except Exception:
            description = ""
        return False, _scrub(f"HTTP {exc.code} {description}".strip(), token)
    except Exception as exc:  # network errors, timeouts
        return False, _scrub(f"{type(exc).__name__}: {exc}", token)
    try:
        parsed = json.loads(body)
    except ValueError:
        return False, _scrub(f"unparseable response: {body[:200]}", token)
    if not parsed.get("ok"):
        return False, _scrub(parsed.get("description", body), token)
    result = parsed.get("result")
    message_id = result.get("message_id") if isinstance(result, dict) else None
    return True, f"message_id={message_id}" if message_id is not None else "message_id unknown"


def _count_text(node: object) -> int:
    if isinstance(node, str):
        return len(node)
    if isinstance(node, list):
        return sum(_count_text(item) for item in node)
    if isinstance(node, dict):
        return sum(_count_text(node[key]) for key in ("text", "cells") if key in node)
    return 0


def _count_blocks(blocks: list) -> int:
    total = 0
    for block in blocks:
        total += 1
        if isinstance(block, dict) and block.get("type") == "table":
            total += len(block.get("cells", []))
    return total


def check_limits(rich_message: object) -> str | None:
    """Return a problem description if the payload exceeds documented limits."""
    if not isinstance(rich_message, dict) or not isinstance(rich_message.get("blocks"), list):
        return "payload has no 'blocks' list"
    blocks = rich_message["blocks"]
    if _count_blocks(blocks) > MAX_RICH_BLOCKS:
        return f"more than {MAX_RICH_BLOCKS} blocks"
    if _count_text(blocks) > MAX_RICH_CHARS:
        return f"more than {MAX_RICH_CHARS} characters"
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "table":
            if any(len(row) > MAX_TABLE_COLUMNS for row in block.get("cells", [])):
                return f"table with more than {MAX_TABLE_COLUMNS} columns"
    return None


def send_rich(token: str, chat_id: str, rich_message: dict) -> tuple[bool, str]:
    body = json.dumps({"chat_id": chat_id, "rich_message": rich_message}).encode("utf-8")
    return _post(
        f"https://api.telegram.org/bot{token}/sendRichMessage",
        body,
        {"Content-Type": "application/json"},
        token,
    )


def build_plain_message() -> str:
    report_text = (
        REPORT_PATH.read_text(encoding="utf-8") if REPORT_PATH.exists() else "No report generated."
    )
    if len(report_text) > MAX_PLAIN_CHARS:
        allowed_main = max(MAX_PLAIN_CHARS - len(TRUNCATION_SUFFIX), 0)
        return report_text[:allowed_main] + TRUNCATION_SUFFIX
    return report_text[:MAX_PLAIN_CHARS]


def send_plain(token: str, chat_id: str) -> tuple[bool, str]:
    data = urlencode(
        {
            "chat_id": chat_id,
            "text": build_plain_message(),
            "disable_web_page_preview": "true",
        }
    ).encode("utf-8")
    return _post(f"https://api.telegram.org/bot{token}/sendMessage", data, {}, token)


def main() -> int:
    required = ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print(f"Skipping Telegram delivery. Missing secrets: {', '.join(missing)}")
        return 0
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    rich_message = None
    if RICH_PAYLOAD_PATH.exists():
        try:
            rich_message = json.loads(RICH_PAYLOAD_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"Rich payload unreadable, falling back to plain message: {_scrub(exc, token)}")
    else:
        print(f"{RICH_PAYLOAD_PATH} not found, falling back to plain message.")

    if rich_message is not None:
        problem = check_limits(rich_message)
        if problem:
            print(f"Rich payload rejected locally ({problem}), falling back to plain message.")
        else:
            ok, detail = send_rich(token, chat_id, rich_message)
            if ok:
                print(f"Telegram rich message sent ({detail})")
                return 0
            print(f"sendRichMessage failed, falling back to plain message: {detail}")

    ok, detail = send_plain(token, chat_id)
    if ok:
        print(f"Telegram message sent ({detail})")
        return 0
    print(f"Telegram plain message failed: {detail}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
