"""
Single-shot stock check for the Norge Hjemmedrakt — runs once, then exits.
GitHub Actions handles the scheduling. Notifies via ntfy.sh on a hit.
"""

import json
import os
import re
import sys
from datetime import datetime

import requests

PRODUCT_URL = "https://www.unisportstore.no/fotballdrakter/norge-hjemmedrakt-world-cup-2026/461740/"
TARGET_SIZE = "XL"

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "").strip()
NTFY_URL   = f"https://ntfy.sh/{NTFY_TOPIC}" if NTFY_TOPIC else None

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "nb-NO,nb;q=0.9,en;q=0.8",
}


def log(msg: str) -> None:
    print(f"[{datetime.utcnow().isoformat(timespec='seconds')}Z] {msg}", flush=True)


def extract_next_data(html: str):
    m = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        html, re.DOTALL,
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def find_variants(obj):
    SIZE_KEYS  = {"size", "sizeName", "sizeLabel", "name", "label", "title"}
    STOCK_KEYS = {"inStock", "available", "isInStock", "stock",
                  "availability", "stockStatus", "quantity"}
    found = []

    def walk(node):
        if isinstance(node, dict):
            keys = set(node.keys())
            if keys & SIZE_KEYS and keys & STOCK_KEYS:
                found.append(node)
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(obj)
    return found


def normalize(s: str) -> str:
    return re.sub(r"[\s\-_]", "", str(s)).upper()


def variant_size_label(v: dict) -> str:
    for k in ("size", "sizeName", "sizeLabel", "name", "label", "title"):
        if k in v and v[k]:
            return str(v[k])
    return ""


def variant_in_stock(v: dict):
    if "inStock"   in v: return bool(v["inStock"])
    if "isInStock" in v: return bool(v["isInStock"])
    if "available" in v: return bool(v["available"])
    if "stockStatus" in v:
        return str(v["stockStatus"]).lower() in {"instock", "in_stock", "available", "yes"}
    if "availability" in v:
        return str(v["availability"]).lower() in {"instock", "in_stock", "available", "yes"}
    if "stock" in v:
        try: return int(v["stock"]) > 0
        except: pass
    if "quantity" in v:
        try: return int(v["quantity"]) > 0
        except: pass
    return None


def check_size_available(html: str, target: str):
    data = extract_next_data(html)
    target_norm = normalize(target)
    if data:
        variants = find_variants(data)
        matches  = [v for v in variants if normalize(variant_size_label(v)) == target_norm]
        if matches:
            for v in matches:
                if variant_in_stock(v) is True:
                    return True, f"JSON variant in stock: {variant_size_label(v)}"
            return False, f"JSON found {len(matches)} variant(s) for {target} but none in stock"
        debug = f"JSON parsed, no variant for {target} ({len(variants)} variants total)"
    else:
        debug = "No __NEXT_DATA__ block found"

    fallback = re.search(
        rf'"size"\s*:\s*"{re.escape(target)}"[^{{}}]{{0,200}}'
        rf'("inStock"\s*:\s*true|"available"\s*:\s*true|"stock"\s*:\s*[1-9])',
        html, re.IGNORECASE,
    )
    if fallback:
        return True, "HTML fallback matched in-stock pattern"
    return False, debug


def send_ntfy(title: str, message: str) -> None:
    if not NTFY_URL:
        log("NTFY_TOPIC not set — skipping push notification.")
        return
    try:
        requests.post(
            NTFY_URL,
            data=message.encode("utf-8"),
            headers={
                "Title": title,
                "Priority": "5",
                "Tags": "shopping_cart,norway",
                "Click": PRODUCT_URL,
                "Actions": f"view, Buy now, {PRODUCT_URL}",
            },
            timeout=15,
        )
        log("ntfy push sent.")
    except Exception as e:
        log(f"ntfy push failed: {e}")


def main() -> int:
    log(f"Checking {TARGET_SIZE} on Unisport…")
    try:
        r = requests.get(PRODUCT_URL, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception as e:
        log(f"Fetch failed: {e}")
        return 0  # don't fail the workflow on transient errors

    available, info = check_size_available(r.text, TARGET_SIZE)
    if available:
        log(f"✅ {TARGET_SIZE} IS AVAILABLE — {info}")
        send_ntfy(
            f"Norge jersey: {TARGET_SIZE} in stock!",
            f"Tap to buy now.\n{PRODUCT_URL}",
        )
    else:
        log(f"❌ {TARGET_SIZE} not available — {info}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
