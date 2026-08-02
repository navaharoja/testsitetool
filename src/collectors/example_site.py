import hashlib
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

SOURCE = "example_site"
DEFAULT_URL = "https://books.toscrape.com/"
DEFAULT_UA = "Mozilla/5.0 (X11; Linux x86_64) ScrapingDatosBot/1.0"


def _fetch_html(url: str, timeout: int = 20, retries: int = 3, user_agent: Optional[str] = None) -> str:
    headers = {"User-Agent": user_agent or DEFAULT_UA}
    last_err: Optional[Exception] = None
    for _ in range(max(1, retries)):
        try:
            resp = requests.get(url, headers=headers, timeout=timeout)
            resp.raise_for_status()
            return resp.text
        except requests.RequestException as exc:
            last_err = exc
            time.sleep(1)
    raise RuntimeError(f"Failed to fetch {url}") from last_err


def _abs_url(base: str, href: str) -> str:
    if href.startswith("http://") or href.startswith("https://"):
        return href
    if base.endswith("/") and href.startswith("/"):
        return base[:-1] + href
    if not base.endswith("/") and not href.startswith("/"):
        return base + "/" + href
    return base + href


def _parse_price(text: str) -> float:
    cleaned = text.replace("£", "").replace("$", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def collect(limit: int = 50, url: str = DEFAULT_URL, timeout: int = 20, retries: int = 3) -> List[Dict]:
    html = _fetch_html(url, timeout=timeout, retries=retries)
    soup = BeautifulSoup(html, "lxml")

    items: List[Dict] = []
    ts = datetime.now(timezone.utc).isoformat()

    for card in soup.select(".product_pod"):
        title_el = card.select_one("h3 a")
        price_el = card.select_one(".price_color")
        avail_el = card.select_one(".availability")
        if not title_el or not price_el:
            continue

        title = title_el.get("title", "").strip()
        href = title_el.get("href", "").strip()
        item_url = _abs_url(url, href)

        price_text = price_el.get_text(strip=True)
        price = _parse_price(price_text)

        item_id = hashlib.sha1(item_url.encode("utf-8")).hexdigest()

        items.append(
            {
                "source": SOURCE,
                "id": item_id,
                "title": title,
                "url": item_url,
                "price": price,
                "currency": "GBP",
                "ts_collected": ts,
                "raw": {
                    "price_text": price_text,
                    "availability": avail_el.get_text(strip=True) if avail_el else "",
                },
            }
        )

        if len(items) >= limit:
            break

    return items


if __name__ == "__main__":
    data = collect(limit=5)
    for row in data:
        print(row)
