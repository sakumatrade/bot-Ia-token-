#!/usr/bin/env bash
# Packages "DominusBot.app" into DominusBot.dmg with the standard
# drag-to-Applications layout (spec section 49: download -> open -> drag
# to Applications -> open).
#
# Must run on macOS (uses hdiutil). Run scripts/build_mac.sh first.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build"
APP_NAME="DominusBot"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
DMG_PATH="$BUILD_DIR/DominusBot.dmg"
STAGING_DIR="$BUILD_DIR/dmg-staging"

if [ ! -d "$APP_BUNDLE" ]; then
  echo "error: $APP_BUNDLE not found. Run scripts/build_mac.sh first." >&2
  exit 1
fi

echo "==> Staging DMG contents"
rm -rf "$STAGING_DIR"
mkdir -p "$STAGING_DIR"
cp -R "$APP_BUNDLE" "$STAGING_DIR/"
ln -s /Applications "$STAGING_DIR/Applications"

echo "==> Creating $DMG_PATH"
rm -f "$DMG_PATH"
hdiutil create -volname "DominusBot" \
  -srcfolder "$STAGING_DIR" \
  -ov -format UDZO \
  "$DMG_PATH"

rm -rf "$STAGING_DIR"

echo "==> Done: $DMG_PATH"
echo "    Unsigned DMG — Gatekeeper will warn on any Mac other than the one"
echo "    that built it. To distribute more broadly: scripts/notarize.sh."
