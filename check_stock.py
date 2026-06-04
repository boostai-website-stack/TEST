"""
Stock check for Norge jerseys — single run, exits when done.
Monitors multiple products, each with its own target sizes.
Sends one ntfy push per product when any of its target sizes are in stock.
"""

import os
import re
import sys
from datetime import datetime
from urllib.parse import quote

import requests

PRODUCTS = [
    {
        "name":  "Hjemmedrakt",
        "url":   "https://www.unisportstore.no/fotballdrakter/norge-hjemmedrakt-world-cup-2026/461740/",
        "id":    "461740",
        "sizes": ["XL", "XXXXXL"],
    },
    {
        "name":  "Bortedrakt",
        "url":   "https://www.unisportstore.no/fotballdrakter/norge-bortedrakt-world-cup-2026/461742/",
        "id":    "461742",
        "sizes": ["XL", "XXXXXL"],
    },
]

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


def fetch_html(url: str, product_id: str) -> str | None:
    encoded = quote(url, safe="")
    for proxy in PROXIES:
        name = proxy.split("//")[1].split("/")[0]
        try:
            r = requests.get(proxy + encoded, headers=HEADERS, timeout=30)
            r.raise_for_status()
            html = r.text
            if product_id in html:
                log(f"  {name}: {len(html)} bytes ✓")
                return html
            log(f"  {name}: {len(html)} bytes, product ID missing — trying next")
        except Exception as e:
            log(f"  {name}: {e} — trying next")
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


def send_ntfy(title: str, message: str, click_url: str) -> None:
    if not NTFY_URL:
        log("NTFY_TOPIC not set — skipping push notification.")
        return
    try:
        requests.post(
            NTFY_URL,
            data=message.encode("utf-8"),
            headers={
                "Title": title, "Priority": "5",
                "Tags": "shopping_cart,norway",
                "Click": click_url,
                "Actions": f"view, Buy now, {click_url}",
            },
            timeout=15,
        )
        log("  ntfy push sent.")
    except Exception as e:
        log(f"  ntfy push failed: {e}")


def check_product(product: dict) -> None:
    name  = product["name"]
    url   = product["url"]
    sizes = product["sizes"]
    log(f"== {name} (sizes: {sizes}) ==")

    html = fetch_html(url, product["id"])
    if html is None:
        log(f"  All proxies failed for {name}.")
        return

    available = []
    for size in sizes:
        ok, info = check_size_available(html, size)
        if ok:
            log(f"  ✅ {size} — {info}")
            available.append(size)
        else:
            log(f"  ❌ {size} — {info}")

    if available:
        sizes_str = ", ".join(available)
        send_ntfy(
            title     = f"{name}: {sizes_str} in stock!",
            message   = f"Tap to buy now.\n{url}",
            click_url = url,
        )


def main() -> int:
    for product in PRODUCTS:
        check_product(product)
    return 0


if __name__ == "__main__":
    sys.exit(main())
