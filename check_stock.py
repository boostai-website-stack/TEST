"""
Stock check for the Norge Hjemmedrakt — single run, exits when done.
Monitors one or more sizes. Sends a single ntfy push per run listing
whichever target sizes are currently in stock.
"""

import os
import re
import sys
from datetime import datetime
from urllib.parse import quote

import requests

PRODUCT_URL  = "https://www.unisportstore.no/fotballdrakter/norge-hjemmedrakt-world-cup-2026/461740/"
TARGET_SIZES = ["XL", "L"]   # add or remove sizes here
PRODUCT_ID   = "461740"

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_URL   = f"https://ntfy.sh/{NTFY_TOPIC}" if NTFY_TOPIC else None

PROXIES = [
    "https://api.codetabs.com/v1/proxy?quest=",
    "https://api.allorigins.win/raw?url=",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "nb-NO,nb;q=0.9,en;q=0.8",
}

IN_STOCK_VALUES = {"in stock", "instock", "in_stock", "available", "yes"}


def log(msg: str) -> None:
    print(f"[{datetime.utcnow().isoformat(timespec='seconds')}Z] {msg}", flush=True)


def fetch_html() -> str | None:
    encoded = quote(PRODUCT_URL, safe="")
    for proxy in PROXIES:
        name = proxy.split("//")[1].split("/")[0]
        try:
            r = requests.get(proxy + encoded, headers=HEADERS, timeout=30)
            r.raise_for_status()
            html = r.text
            if PRODUCT_ID in html:
                log(f"{name}: {len(html)} bytes ✓")
                return html
            log(f"{name}: {len(html)} bytes, product ID missing — trying next")
        except Exception as e:
            log(f"{name}: {e} — trying next")
    return None


def check_size_available(html: str, target: str) -> tuple[bool, str]:
    target_esc = re.escape(target)
    pattern = (
        r'\\"name\\":\\"' + target_esc + r'\\"'
        r'.{0,1000}?'
        r'\\"availability\\":\\"([^"\\]+)\\"'
    )
    m = re.search(pattern, html, re.DOTALL)
    if m:
        availability = m.group(1).strip().lower()
        if availability in IN_STOCK_VALUES:
            return True, f"availability = '{m.group(1)}'"
        return False, f"availability = '{m.group(1)}'"
    if re.search(r'\\"name\\":\\"' + target_esc + r'\\"', html):
        return False, f"variant '{target}' present but no availability field nearby"
    return False, f"variant '{target}' not found in page data"


def send_ntfy(title: str, message: str) -> None:
    if not NTFY_URL:
        log("NTFY_TOPIC not set — skipping push notification.")
        return
    try:
        requests.post(
            NTFY_URL,
            data=message.encode("utf-8"),
            headers={
                "Title": title, "Priority": "5",
                "Tags": "shopping_cart,norway", "Click": PRODUCT_URL,
                "Actions": f"view, Buy now, {PRODUCT_URL}",
            },
            timeout=15,
        )
        log("ntfy push sent.")
    except Exception as e:
        log(f"ntfy push failed: {e}")


def main() -> int:
    log(f"Checking sizes {TARGET_SIZES} on Unisport…")
    html = fetch_html()
    if html is None:
        log("All proxies failed — will try again next run.")
        return 0

    available_sizes: list[str] = []
    for size in TARGET_SIZES:
        ok, info = check_size_available(html, size)
        if ok:
            log(f"✅ {size} IS AVAILABLE — {info}")
            available_sizes.append(size)
        else:
            log(f"❌ {size} not available — {info}")

    if available_sizes:
        sizes_str = ", ".join(available_sizes)
        send_ntfy(
            f"Norge jersey: {sizes_str} in stock!",
            f"Tap to buy now.\n{PRODUCT_URL}",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
