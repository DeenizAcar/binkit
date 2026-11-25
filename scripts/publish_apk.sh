#!/usr/bin/env bash
# Build the release APK and publish it with the download page to GitHub Pages.
#
#   scripts/publish_apk.sh "status text shown on the page"
#
# The gh-pages branch holds only the latest build: it is rebuilt as a single
# orphan commit and force-pushed each time, so old 50 MB APKs don't pile up in
# the repository history. Page: https://deenizacar.github.io/binkit/
set -euo pipefail

STATUS="${1:-Test build.}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APK="$REPO_ROOT/app/build/app/outputs/flutter-apk/app-release.apk"

if [[ "${SKIP_BUILD:-0}" != "1" ]]; then
  (cd "$REPO_ROOT/app" && flutter build apk --release --target-platform android-arm,android-arm64)
fi

VERSION="$(grep '^version:' "$REPO_ROOT/app/pubspec.yaml" | awk '{print $2}')+$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
SIZE="$(du -m "$APK" | cut -f1) MB"
DATE="$(date -u +%Y-%m-%d)"
SHA="$(sha256sum "$APK" | cut -d' ' -f1)"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp "$APK" "$WORK/bink-it.apk"
python - "$REPO_ROOT/site/index.html" "$WORK/index.html" "$VERSION" "$SIZE" "$DATE" "$SHA" "$STATUS" <<'PY'
import html, sys
src, dst, version, size, date, sha, status = sys.argv[1:]
page = open(src, encoding="utf-8").read()
for key, value in {"VERSION": version, "SIZE": size, "DATE": date, "SHA256": sha, "STATUS": status}.items():
    page = page.replace("{{" + key + "}}", html.escape(value))
open(dst, "w", encoding="utf-8").write(page)
PY
touch "$WORK/.nojekyll"

cd "$WORK"
git init -q -b gh-pages
git add -A
git -c user.name="$(git -C "$REPO_ROOT" config user.name)" \
    -c user.email="$(git -C "$REPO_ROOT" config user.email)" \
    commit -qm "Publish test build $VERSION"
git push -qf "$(git -C "$REPO_ROOT" remote get-url origin)" gh-pages:gh-pages
echo "published $VERSION ($SIZE) to gh-pages"
