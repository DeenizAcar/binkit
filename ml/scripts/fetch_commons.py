"""Build the car-brand image set from Wikimedia Commons.

Only public-domain, CC0 and CC BY images are kept (no CC BY-SA, GFDL, NC or
ND; see ml/DATASETS.md). Uses the official MediaWiki API, one request at a
time, with maxlag and backoff, which is how Wikimedia asks bots to behave.
Standard library only.

Usage (run from the repo root):
  python -I ml/scripts/fetch_commons.py check
  python -I ml/scripts/fetch_commons.py fetch --per-brand 400 [--only Toyota] [--dry-run]
  python -I ml/scripts/fetch_commons.py credits

Images go to ml/data/commons/<brand>/ (git-ignored) with a manifest.csv.
After manual cleaning (delete wrong images), `credits` writes
app/assets/data/image_credits.txt for the photos that are still there.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
REPO = Path(__file__).resolve().parents[2]
BRANDS_FILE = REPO / "ml" / "brands.tsv"
OUT_DIR = REPO / "ml" / "data" / "commons"
CREDITS_FILE = REPO / "app" / "assets" / "data" / "image_credits.txt"
MANIFEST_FIELDS = ["brand", "pageid", "title", "author", "license", "page_url", "file"]

# Wikimedia asks for a descriptive User-Agent; add contact info with --user-agent.
DEFAULT_UA = "car-dataset-builder/0.1 (educational dataset tool; python-urllib)"

# Accepted values of the extmetadata "License" field.
ALLOWED_LICENSE = re.compile(r"^(pd|cc0|cc-by-\d(\.\d)?)$")
# Short-name fallback when "License" is missing.
ALLOWED_SHORT = re.compile(r"^(public domain|cc0( 1\.0)?|cc by \d(\.\d)?)$", re.I)
FORBIDDEN = re.compile(r"\b(sa|nc|nd|gfdl|share ?alike|noncommercial|noderiv)", re.I)

# Subcategories / files that are not photos of whole cars.
SKIP = re.compile(
    r"interior|dashboard|steering|seat(s)? |engine|motor |logo|emblem|badge|"
    r"wheel|rim|hubcap|tail ?light|head ?light|grille|key|brochure|advert|"
    r"scale model|model car|toy|diecast|die-cast|lego|drawing|illustration|"
    r"in art|patent|factory|plant|assembly|crash|accident|wreck|scrap|"
    r"museum interior|racing|rally|race car|ambulance|police|taxi|"
    r"trucks|buses|motorcycles|people with|license plate|number plate|"
    r"registration plate|\.svg$|\.pdf$|\.tif",
    re.I,
)


class Commons:
    def __init__(self, user_agent: str):
        self.ua = user_agent

    def get(self, params: dict) -> dict:
        params = {**params, "format": "json", "formatversion": "2", "maxlag": "5"}
        url = API + "?" + urllib.parse.urlencode(params)
        for attempt in range(6):
            req = urllib.request.Request(url, headers={"User-Agent": self.ua})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = json.load(r)
            except urllib.error.HTTPError as e:
                if e.code in (429, 503):
                    time.sleep(int(e.headers.get("Retry-After", 5 * (attempt + 1))))
                    continue
                raise
            if data.get("error", {}).get("code") == "maxlag":
                time.sleep(5 * (attempt + 1))
                continue
            if "error" in data:
                raise RuntimeError(data["error"])
            return data
        raise RuntimeError("Commons API kept refusing (maxlag / rate limit)")

    def paged(self, params: dict):
        cont: dict = {}
        while True:
            data = self.get({**params, **cont})
            yield data
            if "continue" not in data:
                return
            cont = data["continue"]

    def exists(self, category: str) -> int | None:
        data = self.get({
            "action": "query",
            "prop": "categoryinfo",
            "titles": f"Category:{category}",
        })
        page = data["query"]["pages"][0]
        if page.get("missing"):
            return None
        return page.get("categoryinfo", {}).get("size", 0)

    def subcats(self, category: str):
        for data in self.paged({
            "action": "query",
            "list": "categorymembers",
            "cmtitle": f"Category:{category}",
            "cmtype": "subcat",
            "cmlimit": "500",
        }):
            for m in data["query"]["categorymembers"]:
                yield m["title"].removeprefix("Category:")

    def files(self, category: str):
        for data in self.paged({
            "action": "query",
            "generator": "categorymembers",
            "gcmtitle": f"Category:{category}",
            "gcmtype": "file",
            "gcmlimit": "50",
            "prop": "imageinfo",
            "iiprop": "url|mime|extmetadata",
            "iiurlwidth": "640",
            "iiextmetadatafilter": "License|LicenseShortName|Artist",
        }):
            yield from data.get("query", {}).get("pages", [])


def meta(info: dict, key: str) -> str:
    return str(info.get("extmetadata", {}).get(key, {}).get("value", "")).strip()


def clean_text(value: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", " ", value))
    return re.sub(r"\s+", " ", text).replace("|", "/").strip()


def accepted_license(info: dict) -> str | None:
    """Returns the license short name if allowed, else None."""
    lic = meta(info, "License").lower()
    short = clean_text(meta(info, "LicenseShortName"))
    if FORBIDDEN.search(lic) or FORBIDDEN.search(short):
        return None
    if ALLOWED_LICENSE.match(lic) or ALLOWED_SHORT.match(short):
        return short or lic
    return None


def slug(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def read_brands(only: list[str] | None) -> list[tuple[str, str]]:
    brands = []
    for line in BRANDS_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        label, category = (part.strip() for part in line.split("\t"))
        if not only or label in only:
            brands.append((label, category))
    return brands


def collect(api: Commons, category: str, limit: int, max_depth: int, stats: dict):
    """Breadth-first walk of a brand category; yields accepted file pages."""
    queue = deque([(category, 0)])
    seen_cats = {category}
    found = 0
    while queue and found < limit:
        cat, depth = queue.popleft()
        for page in api.files(cat):
            info = (page.get("imageinfo") or [{}])[0]
            stats["seen"] += 1
            if info.get("mime") != "image/jpeg" or SKIP.search(page["title"]):
                stats["skipped"] += 1
                continue
            lic = accepted_license(info)
            if lic is None:
                stats["license_rejected"] += 1
                continue
            yield page, info, lic
            found += 1
            if found >= limit:
                return
        if depth < max_depth:
            for sub in api.subcats(cat):
                if sub not in seen_cats and not SKIP.search(sub):
                    seen_cats.add(sub)
                    queue.append((sub, depth + 1))


def cmd_check(api: Commons, args) -> int:
    missing = 0
    for label, category in read_brands(args.only):
        size = api.exists(category)
        print(f"{label:15} {category:35} {'MISSING' if size is None else size}")
        missing += size is None
    return 1 if missing else 0


def cmd_fetch(api: Commons, args) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT_DIR / "manifest.csv"
    rows: dict[int, dict] = {}
    if manifest_path.exists():
        with manifest_path.open(encoding="utf-8", newline="") as f:
            rows = {int(r["pageid"]): r for r in csv.DictReader(f)}

    owner = {pid: r["brand"] for pid, r in rows.items()}
    conflicts: set[int] = set()

    for label, category in read_brands(args.only):
        stats = {"seen": 0, "skipped": 0, "license_rejected": 0}
        licenses: dict[str, int] = {}
        kept = 0
        brand_dir = OUT_DIR / slug(label)
        for page, info, lic in collect(api, category, args.per_brand, args.depth, stats):
            pid = page["pageid"]
            if pid in owner and owner[pid] != label:
                conflicts.add(pid)  # same photo under two brands: ambiguous
                continue
            licenses[lic] = licenses.get(lic, 0) + 1
            kept += 1
            if args.dry_run or pid in rows:
                continue
            target = brand_dir / f"{pid}.jpg"
            brand_dir.mkdir(parents=True, exist_ok=True)
            req = urllib.request.Request(info["thumburl"], headers={"User-Agent": api.ua})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    target.write_bytes(r.read())
            except urllib.error.URLError as e:
                print(f"  download failed {page['title']}: {e}", file=sys.stderr)
                continue
            rows[pid] = {
                "brand": label,
                "pageid": pid,
                "title": page["title"],
                "author": clean_text(meta(info, "Artist")) or "Unknown",
                "license": lic,
                "page_url": info.get("descriptionurl", ""),
                "file": str(target.relative_to(OUT_DIR)).replace("\\", "/"),
            }
            owner[pid] = label
            time.sleep(0.2)
        top = ", ".join(f"{k}: {v}" for k, v in sorted(licenses.items(), key=lambda x: -x[1])[:4])
        print(f"{label:15} kept {kept:4}  (seen {stats['seen']}, skipped {stats['skipped']}, "
              f"license-rejected {stats['license_rejected']})  [{top}]")

    for pid in conflicts:
        row = rows.pop(pid, None)
        if row:
            (OUT_DIR / row["file"]).unlink(missing_ok=True)
    if conflicts:
        print(f"Dropped {len(conflicts)} photos that appear under more than one brand.")

    if not args.dry_run:
        with manifest_path.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
            w.writeheader()
            w.writerows(sorted(rows.values(), key=lambda r: (r["brand"], int(r["pageid"]))))
    return 0


def cmd_credits(_api, _args) -> int:
    manifest_path = OUT_DIR / "manifest.csv"
    with manifest_path.open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (OUT_DIR / r["file"]).exists()]
    lines = [
        "# Photo credits for training images. Generated by ml/scripts/fetch_commons.py.",
        "# Format: title | author | license | source URL",
    ]
    for r in sorted(rows, key=lambda r: r["title"].lower()):
        lines.append(f"{r['title']} | {r['author']} | {r['license']} | {r['page_url']}")
    CREDITS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} credits to {CREDITS_FILE.relative_to(REPO)}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["check", "fetch", "credits"])
    p.add_argument("--only", nargs="*", help="brand labels to process")
    p.add_argument("--per-brand", type=int, default=400)
    p.add_argument("--depth", type=int, default=4, help="max subcategory depth")
    p.add_argument("--dry-run", action="store_true", help="count only, download nothing")
    p.add_argument("--user-agent", default=DEFAULT_UA)
    args = p.parse_args()
    api = Commons(args.user_agent)
    return {"check": cmd_check, "fetch": cmd_fetch, "credits": cmd_credits}[args.command](api, args)


if __name__ == "__main__":
    sys.exit(main())
