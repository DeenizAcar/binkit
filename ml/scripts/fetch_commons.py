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
Photos whose title names another brand in brands.tsv are skipped (e.g.
Daihatsu or Subaru models that sit under Toyota's category tree).
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
    r"\b("
    r"interior|dashboard|steering wheel|seats?|engine|logo|emblem|badge|"
    r"wheels?|rims?|hubcaps?|tail ?lights?|head ?lights?|grille|keys?|brochure|advert\w*|"
    r"scale model|model car|toys?|diecast|die-cast|lego|drawing|illustration|"
    r"patent|factory|assembly line|crash|accident|wreck|scrap\w*|"
    r"racing|rally|race car|ambulance|police|taxi|"
    r"trucks?|bus|buses|motorcycles?|license plate|number plate|registration plate"
    r")\b"
    r"|\.(svg|pdf|tiff?)$",
    re.I,
)


class Commons:
    def __init__(self, user_agent: str):
        self.ua = user_agent

    def get(self, params: dict) -> dict:
        params = {**params, "format": "json", "formatversion": "2", "maxlag": "5"}
        url = API + "?" + urllib.parse.urlencode(params)
        for attempt in range(10):
            req = urllib.request.Request(url, headers={"User-Agent": self.ua})
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    data = json.load(r)
            except urllib.error.HTTPError as e:
                if e.code in (429, 503):
                    time.sleep(int(e.headers.get("Retry-After", 5 * (attempt + 1))))
                    continue
                raise
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                # Network drop (e.g. DNS failure): wait and retry.
                print(f"  network error ({e}), retrying", file=sys.stderr)
                time.sleep(30 * (attempt + 1))
                continue
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

    def search_files(self, query: str):
        for data in self.paged({
            "action": "query",
            "generator": "search",
            "gsrsearch": query,
            "gsrnamespace": "6",
            "gsrlimit": "50",
            "prop": "imageinfo",
            "iiprop": "url|mime|extmetadata",
            "iiurlwidth": "500",  # a standard Wikimedia thumbnail size (w.wiki/GHai),
            "iiextmetadatafilter": "License|LicenseShortName|Artist",
        }):
            pages = data.get("query", {}).get("pages", [])
            yield from sorted(pages, key=lambda p: p.get("index", 0))
            time.sleep(1)  # be gentle: at most ~1 API request per second

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


def collect(api: Commons, category: str, limit: int, other_brands: list[str], stats: dict):
    """Yields accepted files using CirrusSearch: deepcategory + license filter.

    One query per license class, so most rejected files never leave the API.
    """
    # Case-sensitive whole words, so "Mini" doesn't hit "minivan" or "SEAT" "seat".
    other = (re.compile(r"\b(" + "|".join(re.escape(b) for b in other_brands) + r")\b")
             if other_brands else None)
    found = 0
    for license_class in ("unrestricted", "attribution"):
        query = f'deepcategory:"{category}" haslicense:{license_class} filemime:image/jpeg'
        for page in api.search_files(query):
            info = (page.get("imageinfo") or [{}])[0]
            stats["seen"] += 1
            title = page["title"]
            if SKIP.search(title) or (other and other.search(title)):
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
        if found >= limit:
            return


def safe_collect(api, category, limit, others, stats, label):
    """collect(), but an API outage only ends this brand; the next run resumes it."""
    try:
        yield from collect(api, category, limit, others, stats)
    except RuntimeError as e:
        print(f"{label}: stopped early ({e}); rerun to resume", file=sys.stderr, flush=True)


def cmd_check(api: Commons, args) -> int:
    missing = 0
    for label, category in read_brands(args.only):
        size = api.exists(category)
        print(f"{label:15} {category:35} {'MISSING' if size is None else size}")
        missing += size is None
    return 1 if missing else 0


def download(url: str, target: Path, ua: str) -> bool:
    """Downloads one thumbnail, backing off on HTTP 429/503."""
    for attempt in range(5):
        req = urllib.request.Request(url, headers={"User-Agent": ua})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                target.write_bytes(r.read())
            return True
        except urllib.error.HTTPError as e:
            if e.code in (429, 503):
                wait = int(e.headers.get("Retry-After") or 60 * (attempt + 1))
                print(f"  rate limited, waiting {wait}s", file=sys.stderr)
                time.sleep(wait)
                continue
            print(f"  download failed ({e.code}): pageid {target.stem}", file=sys.stderr)
            return False
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            print(f"  network error ({e}), retrying pageid {target.stem}", file=sys.stderr)
            time.sleep(30 * (attempt + 1))
    return False


def write_manifest(path: Path, rows: dict[int, dict]) -> None:
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
        w.writeheader()
        w.writerows(sorted(rows.values(), key=lambda r: (r["brand"], int(r["pageid"]))))
    tmp.replace(path)


def cmd_fetch(api: Commons, args) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = OUT_DIR / "manifest.csv"
    rows: dict[int, dict] = {}
    if manifest_path.exists():
        with manifest_path.open(encoding="utf-8", newline="") as f:
            rows = {int(r["pageid"]): r for r in csv.DictReader(f)}

    owner = {pid: r["brand"] for pid, r in rows.items()}
    conflicts: set[int] = set()

    all_labels = [label for label, _ in read_brands(None)]
    for label, category in read_brands(args.only):
        have = sum(1 for r in rows.values() if r["brand"] == label)
        if not args.dry_run and have >= args.per_brand:
            print(f"{label:15} already has {have}, skipping")
            continue
        others = [b for b in all_labels if b.lower() != label.lower()]
        stats = {"seen": 0, "skipped": 0, "license_rejected": 0}
        licenses: dict[str, int] = {}
        kept = 0
        brand_dir = OUT_DIR / slug(label)
        for page, info, lic in safe_collect(api, category, args.per_brand, others, stats, label):
            pid = page["pageid"]
            if pid in owner and owner[pid] != label:
                conflicts.add(pid)  # same photo under two brands: ambiguous
                continue
            if not args.dry_run and pid not in rows:
                target = brand_dir / f"{pid}.jpg"
                brand_dir.mkdir(parents=True, exist_ok=True)
                # Files from an interrupted run are reused, not re-downloaded.
                if not target.exists():
                    if not download(info["thumburl"], target, api.ua):
                        continue
                    time.sleep(1)  # polite pace for upload.wikimedia.org
                rows[pid] = {
                    "brand": label,
                    "pageid": pid,
                    "title": page["title"],
                    "author": clean_text(meta(info, "Artist")) or "Unknown",
                    "license": lic,
                    # Link by page id: file titles often contain plate numbers,
                    # which must not be copied into the app.
                    "page_url": f"https://commons.wikimedia.org/?curid={pid}",
                    "file": str(target.relative_to(OUT_DIR)).replace("\\", "/"),
                }
                owner[pid] = label
            licenses[lic] = licenses.get(lic, 0) + 1
            kept += 1
        top = ", ".join(f"{k}: {v}" for k, v in sorted(licenses.items(), key=lambda x: -x[1])[:4])
        print(f"{label:15} kept {kept:4}  (seen {stats['seen']}, skipped {stats['skipped']}, "
              f"license-rejected {stats['license_rejected']})  [{top}]", flush=True)
        if not args.dry_run:
            write_manifest(manifest_path, rows)  # checkpoint after each brand

    for pid in conflicts:
        row = rows.pop(pid, None)
        if row:
            (OUT_DIR / row["file"]).unlink(missing_ok=True)
    if conflicts:
        print(f"Dropped {len(conflicts)} photos that appear under more than one brand.")
    if not args.dry_run:
        write_manifest(manifest_path, rows)
    return 0


def cmd_credits(_api, _args) -> int:
    manifest_path = OUT_DIR / "manifest.csv"
    with manifest_path.open(encoding="utf-8", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (OUT_DIR / r["file"]).exists()]
    lines = [
        "# Photo credits for training images. Generated by ml/scripts/fetch_commons.py.",
        "# Format: author | license | source URL",
        "# File titles are left out on purpose: many contain license plate numbers.",
    ]
    for r in sorted(rows, key=lambda r: (r["author"].lower(), int(r["pageid"]))):
        lines.append(f"{r['author']} | {r['license']} | {r['page_url']}")
    CREDITS_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} credits to {CREDITS_FILE.relative_to(REPO)}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("command", choices=["check", "fetch", "credits"])
    p.add_argument("--only", nargs="*", help="brand labels to process")
    p.add_argument("--per-brand", type=int, default=400)
    p.add_argument("--dry-run", action="store_true", help="count only, download nothing")
    p.add_argument("--user-agent", default=DEFAULT_UA)
    args = p.parse_args()
    api = Commons(args.user_agent)
    return {"check": cmd_check, "fetch": cmd_fetch, "credits": cmd_credits}[args.command](api, args)


if __name__ == "__main__":
    sys.exit(main())
