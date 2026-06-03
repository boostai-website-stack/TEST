"""
Single-shot stock check for the Norge Hjemmedrakt.
Diagnostic version — prints HTML context around the target size to help us
figure out exactly how Unisport encodes stock data.
"""

import json
import os
import re
import sys
from datetime import datetime
from urllib.parse import quote

import requests

PRODUCT_URL = "https://www.unisportstore.no/fotballdrakter/norge-hjemmedrakt-world-cup-2026/461740/"
TARGET_SIZE = "3XL"
PRODUCT_ID  = "461740"

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_URL   = f"https://ntfy.sh/{NTFY_TOPIC}" if NTFY_TOPIC else None

# codetabs first — it's the one that actually returns real HTML for us.
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


def log(msg: str) -> None:
    print(f"[{datetime.utcnow().isoformat(timespec='seconds')}Z] {msg}", flush=True)


def fetch_html() -> str | None:
    """Try proxies; validate by presence of the product ID in the response."""
    encoded = quote(PRODUCT_URL, safe="")
    for proxy in PROXIES:
        url = proxy + encoded
        name = proxy.split("//")[1].split("/")[0]
        try:
            r = requests.get(url, headers=HEADERS, timeout=30)
            r.raise_for_status()
            html = r.text
            if PRODUCT_ID in html:
                log(f"{name}: {len(html)} bytes, product ID found ✓")
                return html
            log(f"{name}: {len(html)} bytes but product ID missing — trying next")
        except Exception as e:
            log(f"{name}: {e} — trying next")
    return None


def dump_size_context(html: str, target: str) -> None:
    """Print all snippets of HTML around occurrences of the target size."""
    log(f"--- Searching for '{target}' in HTML ---")
    count = 0
    for m in re.finditer(re.escape(target), html):
        count += 1
        if count > 6:
            log(f"  (… {len([1 for _ in re.finditer(re.escape(target), html)]) - 6} more occurrences omitted)")
            break
        start = max(0, m.start() - 120)
        end = min(len(html), m.end() + 250)
        snippet = html[start:end].replace("\n", " ").replace("  ", " ")
        log(f"  [match {count}] …{snippet}…")
    if count == 0:
        log(f"  '{target}' not found in HTML at all.")
    log(f"--- End search ({count} matches found) ---")


def look_for_data_patterns(html: str) -> None:
    """Scan for likely places that contain size/stock data."""
    log("--- Scanning for data containers ---")
    patterns = [
        (r'<script id="__NEXT_DATA__"', "__NEXT_DATA__ script tag"),
        (r'self\.__next_f\.push', "Next.js App Router payload (__next_f)"),
        (r'window\.__INITIAL_STATE__', "Generic window.__INITIAL_STATE__"),
        (r'"variants"\s*:', "JSON 'variants' key"),
        (r'"sizes"\s*:', "JSON 'sizes' key"),
        (r'"inStock"', "JSON 'inStock' key"),
        (r'"available"', "JSON 'available' key"),
        (r'data-size=', "HTML data-size attribute"),
    ]
    for pat, label in patterns:
        hits = len(re.findall(pat, html))
        log(f"  {label}: {hits} occurrences")
    log("--- End scan ---")


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
    log(f"Checking {TARGET_SIZE} on Unisport…")
    html = fetch_html()
    if html is None:
        log("All proxies failed.")
        return 0

    look_for_data_patterns(html)
    dump_size_context(html, TARGET_SIZE)

    # Also try common quick stock checks for now — we'll refine after seeing context.
    quick_in_stock = re.search(
        rf'"3XL"[^{{}}]{{0,200}}("inStock"\s*:\s*true|"available"\s*:\s*true|"stock"\s*:\s*[1-9])',
        html, re.IGNORECASE,
    )
    if quick_in_stock:
        log(f"✅ Quick check says {TARGET_SIZE} is available")
        send_ntfy(
            f"Norge jersey: {TARGET_SIZE} in stock!",
            f"Tap to buy now.\n{PRODUCT_URL}",
        )
    else:
        log(f"❌ Quick check: {TARGET_SIZE} not detected as available")
    return 0


if __name__ == "__main__":
    sys.exit(main())
