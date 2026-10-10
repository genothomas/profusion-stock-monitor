"""Profusion UK stock monitor.

Renders each product page in headless Chromium, parses the live stock
indicator (Magento MSI widget), fires a Discord webhook only on
OOS -> in-stock transition. State persisted to JSON file.
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

TIMEOUT_S = 30
TIMEOUT_MS = TIMEOUT_S * 1000
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)
STOCK_TEXT_RE = re.compile(r"stock\s*:\s*\d+", re.IGNORECASE)
OOS_IMG_RE = re.compile(
    r"/media/catalog/stock/[^/]+/default/(stock-(no|out)|oos)", re.IGNORECASE
)


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def load_state() -> dict[str, bool]:
    p = Path(env("STATE_PATH", "/tmp/profusion_scrap_state.json"))
    if p.exists():
        return json.loads(p.read_text())
    return {}


def save_state(state: dict[str, bool]) -> None:
    p = Path(env("STATE_PATH", "/tmp/profusion_scrap_state.json"))
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=2, sort_keys=True))


def parse_stock(page) -> tuple[bool | None, str]:
    body_text = page.locator("body").inner_text(timeout=TIMEOUT_MS)

    m = STOCK_TEXT_RE.search(body_text)
    if m:
        return True, m.group(0)

    img_srcs = page.eval_on_selector_all(
        "img", "els => els.map(e => e.getAttribute('src') || '')"
    )
    for src in img_srcs:
        if OOS_IMG_RE.search(src):
            return False, f"oos image: {src}"

    snippet = " ".join(s for s in body_text.split() if "stock" in s.lower())[:160]
    return None, f"ambiguous: {snippet!r}"


def notify_discord(webhook_url: str, url: str) -> None:
    requests.post(
        webhook_url,
        json={"content": f"🟢 **IN STOCK**: {url}"},
        timeout=TIMEOUT_S,
    ).raise_for_status()


def main() -> int:
    urls = [u.strip() for u in env("PRODUCT_URLS").split(",") if u.strip()]
    webhook = env("DISCORD_WEBHOOK_URL")
    alert_skus = {s.strip() for s in env("ALERT_SKUS").split(",") if s.strip()}
    force_in_stock = {s.strip() for s in env("DEBUG_FORCE_IN_STOCK").split(",") if s.strip()}
    if not urls:
        print("PRODUCT_URLS empty", file=sys.stderr)
        return 1

    jitter = int(env("JITTER_SECONDS", "3600"))
    if jitter > 0:
        delay = random.randint(0, jitter)
        print(f"sleeping {delay}s (jitter)")
        time.sleep(delay)

    state = load_state()
    exit_code = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1280, "height": 800},
            locale="en-GB",
        )
        page = context.new_page()
        try:
            for url in urls:
                sku = url.rstrip("/").split("/")[-1]
                try:
                    page.goto(url, wait_until="networkidle", timeout=TIMEOUT_MS)
                    page.wait_for_timeout(2000)
                    in_stock, snippet = parse_stock(page)
                except Exception as e:
                    print(f"[{sku}] error: {e}", file=sys.stderr)
                    exit_code = 1
                    continue

                if sku in force_in_stock:
                    in_stock = True
                    snippet = f"FORCED in_stock: {snippet}"

                prev = state.get(sku)
                transition = (
                    prev is not None and in_stock is not None and prev != in_stock
                )
                print(
                    f"[{sku}] in_stock={in_stock} prev={prev} "
                    f"transition={transition} snippet={snippet[:160]!r}"
                )

                if transition and in_stock and webhook:
                    if alert_skus and sku not in alert_skus:
                        print(f"[{sku}] transition skipped (not in ALERT_SKUS)")
                    else:
                        try:
                            notify_discord(webhook, url)
                        except Exception as e:
                            print(f"[{sku}] notify error: {e}", file=sys.stderr)
                            exit_code = 1

                if in_stock is not None:
                    state[sku] = in_stock
        finally:
            browser.close()

    save_state(state)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())