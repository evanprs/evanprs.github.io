#!/usr/bin/env python3
"""generate_map_thumbs.py

Fetches screenshots for map links in index.html using the Thum.io API,
saves them to images/map-thumbs/, then updates index.html with thumbnail
<img> tags before each link.

Usage:
  python generate_map_thumbs.py           # process all missing links
  python generate_map_thumbs.py --test    # process first link only
  python generate_map_thumbs.py add TITLE URL  # add a new map entry

Re-run safely: skips URLs that already have a saved thumbnail.
Dependencies: pip install requests beautifulsoup4
"""

import argparse
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

MAP_LIST_MARKER = "<!-- map-list-end -->"


def url_to_filename(url: str, ext: str = ".png") -> str:
    """Stable, unique filename derived from the URL."""
    return hashlib.sha1(url.encode()).hexdigest()[:12] + ext


CONTENT_TYPE_EXT = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


def find_existing_thumb(url: str) -> Path | None:
    """Return the saved thumbnail for url if it exists (any extension)."""
    stem = hashlib.sha1(url.encode()).hexdigest()[:12]
    for p in THUMBS_DIR.glob(f"{stem}.*"):
        return p
    return None


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


def add_map(title: str, url: str):
    """Fetch a thumbnail and insert a new map <li> into index.html."""
    THUMBS_DIR.mkdir(parents=True, exist_ok=True)

    # Check for duplicates using BeautifulSoup (handles &amp; etc.)
    html = INDEX_HTML.read_text()
    soup = BeautifulSoup(html, "html.parser")
    maps_h2 = soup.find("h2", id="Maps link dump")
    if not maps_h2:
        print("ERROR: Could not find <h2 id='Maps link dump'> in index.html")
        sys.exit(1)
    ul = maps_h2.find_parent("section").find("ul")
    for a in ul.find_all("a"):
        if a["href"] == url:
            print(f"ERROR: URL already in list: {url}")
            sys.exit(1)

    # Fetch thumbnail
    existing = find_existing_thumb(url)
    if existing:
        print(f"Thumbnail already exists: {existing.name}")
        dest = existing
    else:
        print(f"Fetching thumbnail for: {title}")
        dest_stem = THUMBS_DIR / url_to_filename(url, "")
        dest = fetch_screenshot(url, dest_stem)
        if dest:
            print(f"  saved {dest.name}")
        else:
            print("  Failed to fetch thumbnail, adding entry without image")

    # Build new <li>
    if dest:
        img_tag = f'<img alt="" src="images/map-thumbs/{dest.name}" class="map-thumb"/>'
    else:
        img_tag = ""
    new_li = f'              <li>{img_tag}<a href="{escape(url)}">{escape(title)}</a></li>\n'

    # Insert before the marker
    if MAP_LIST_MARKER not in html:
        print(f"ERROR: Could not find {MAP_LIST_MARKER!r} in index.html")
        sys.exit(1)

    html = html.replace(
        f"              {MAP_LIST_MARKER}",
        new_li + f"              {MAP_LIST_MARKER}",
        1,
    )
    INDEX_HTML.write_text(html)
    print(f"Added '{title}' to index.html")


def update_thumbs(test_mode: bool = False):
    """Fetch missing thumbnails and update <img> tags for existing list items."""
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

    # --- Step 1: fetch missing screenshots ---
    for li in items:
        a = li.find("a")
        if not a:
            continue
        url = a["href"]
        text = a.get_text(strip=True)

        if find_existing_thumb(url):
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
        dest = find_existing_thumb(a["href"])
        if dest is None:
            continue

        href = a["href"]
        img_tag = f'<img alt="" src="images/map-thumbs/{dest.name}" class="map-thumb"/>'
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


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--test", action="store_true", help="(update mode) process first link only")

    subparsers = parser.add_subparsers(dest="command")
    add_parser = subparsers.add_parser("add", help="Add a new map entry")
    add_parser.add_argument("title", help="Display title for the map link")
    add_parser.add_argument("url", help="URL of the map")

    args = parser.parse_args()

    if args.command == "add":
        add_map(args.title, args.url)
    else:
        update_thumbs(test_mode=args.test)


if __name__ == "__main__":
    main()
