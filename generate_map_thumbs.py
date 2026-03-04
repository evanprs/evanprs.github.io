#!/usr/bin/env python3
"""generate_map_thumbs.py

Fetches screenshots for map links in index.html using the Thum.io API,
saves them to images/map-thumbs/, then updates index.html with thumbnail
<img> tags before each link.

Usage:
  python generate_map_thumbs.py           # process all missing links
  python generate_map_thumbs.py --test    # process first link only

Re-run safely: skips URLs that already have a saved thumbnail.
Dependencies: pip install requests beautifulsoup4
"""

import hashlib
import sys
import time
from html import escape
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).parent
INDEX_HTML = ROOT / "index.html"
THUMBS_DIR = ROOT / "images" / "map-thumbs"

# Thum.io: width=160, crop=675 → 160×90px (16:9) thumbnails; noanimate prevents GIF output
THUMIO_BASE = "https://image.thum.io/get/noanimate/width/160/crop/675"
DELAY = 1.0  # seconds between requests, to be polite

IMG_STYLE = (
    "height:30px;width:53px;object-fit:cover;"
    "border:1px solid #bbb;border-radius:3px;"
    "vertical-align:middle;margin-right:6px;"
)


def url_to_filename(url: str, ext: str = ".png") -> str:
    """Stable, unique filename derived from the URL."""
    return hashlib.sha1(url.encode()).hexdigest()[:12] + ext


CONTENT_TYPE_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def fetch_screenshot(url: str, dest_stem: Path) -> Path | None:
    """Fetch a screenshot via Thum.io. Returns the saved Path on success, else None."""
    try:
        resp = requests.get(f"{THUMIO_BASE}/{url}", timeout=60)
        resp.raise_for_status()
    except Exception as e:
        print(f"    Error: {e}")
        return None

    content_type = resp.headers.get("content-type", "").split(";")[0].strip()
    if "image" not in content_type:
        print(f"    Unexpected content-type: {content_type}")
        return None

    ext = CONTENT_TYPE_EXT.get(content_type, ".png")
    dest = dest_stem.with_suffix(ext)
    dest.write_bytes(resp.content)
    return dest


def main():
    test_mode = "--test" in sys.argv
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)

    soup = BeautifulSoup(INDEX_HTML.read_text(), "html.parser")

    maps_h2 = soup.find("h2", id="Maps link dump")
    if not maps_h2:
        print("ERROR: Could not find <h2 id='Maps link dump'> in index.html")
        sys.exit(1)

    ul = maps_h2.find_parent("section").find("ul")
    items = ul.find_all("li")

    if test_mode:
        items = items[:1]
        print(f"Test mode: processing 1 link")
    else:
        print(f"Processing {len(items)} links")

    def find_existing(url: str) -> Path | None:
        """Return the saved thumbnail for url if it exists (any extension)."""
        stem = hashlib.sha1(url.encode()).hexdigest()[:12]
        for p in THUMBS_DIR.glob(f"{stem}.*"):
            return p
        return None

    # --- Step 1: fetch missing screenshots ---
    for li in items:
        a = li.find("a")
        if not a:
            continue
        url = a["href"]
        text = a.get_text(strip=True)

        if find_existing(url):
            print(f"  skip (exists): {text}")
            continue

        print(f"  fetching: {text}")
        dest_stem = THUMBS_DIR / url_to_filename(url, "")
        saved = fetch_screenshot(url, dest_stem)
        if saved:
            print(f"    saved {saved.name}")
        else:
            print(f"    failed, continuing")
        time.sleep(DELAY)

    # --- Step 2: update HTML with targeted string replacement (preserves formatting) ---
    html = INDEX_HTML.read_text()
    changed = 0
    for li in ul.find_all("li"):
        a = li.find("a")
        if not a:
            continue
        dest = find_existing(a["href"])
        if dest is None:
            continue

        href = a["href"]
        img_tag = (
            f'<img alt="" class="no-invert" '
            f'src="images/map-thumbs/{dest.name}" '
            f'style="{IMG_STYLE}"/>'
        )
        # Match the exact <a href="..."> for this link; skip if img already precedes it
        target = f'<a href="{escape(href)}">'
        if img_tag in html:
            continue  # already inserted
        if target not in html:
            print(f"    WARNING: could not find anchor for {href}")
            continue
        html = html.replace(target, img_tag + target, 1)
        changed += 1

    if changed:
        INDEX_HTML.write_text(html)
        print(f"\nUpdated index.html ({changed} thumbnails added)")
    else:
        print("\nindex.html already up to date")


if __name__ == "__main__":
    main()
