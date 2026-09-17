#!/usr/bin/env bash
# Builds "DominusBot.app" from the macapp/ Swift package.
#
# Must run on macOS with Xcode/the Swift toolchain installed. This repo's
# Linux CI (.github/workflows/macos-build.yml) only verifies that
# `swift build`/`swift test` succeed on GitHub's macOS runners — it does
# not assemble an app bundle, which needs a real Mac's `swift build -c
# release` output plus this script's bundle assembly.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MACAPP_DIR="$ROOT_DIR/macapp"
BUILD_DIR="$ROOT_DIR/build"
APP_NAME="DominusBot"
EXECUTABLE_NAME="BrokerSakuma"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"

echo "==> Building $EXECUTABLE_NAME (release)"
swift build --package-path "$MACAPP_DIR" -c release

echo "==> Assembling $APP_BUNDLE"
rm -rf "$APP_BUNDLE"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

cp "$MACAPP_DIR/.build/release/$EXECUTABLE_NAME" "$APP_BUNDLE/Contents/MacOS/$EXECUTABLE_NAME"
chmod +x "$APP_BUNDLE/Contents/MacOS/$EXECUTABLE_NAME"
cp "$MACAPP_DIR/Resources/Info.plist" "$APP_BUNDLE/Contents/Info.plist"

if [ -f "$MACAPP_DIR/Resources/AppIcon.icns" ]; then
  cp "$MACAPP_DIR/Resources/AppIcon.icns" "$APP_BUNDLE/Contents/Resources/AppIcon.icns"
else
  echo "    (no AppIcon.icns yet — the app will use the default system icon)"
fi

echo "==> Done: $APP_BUNDLE"
echo "    Unsigned. Good enough to run locally on this same Mac (right-click"
echo "    → Open the first time, to get past Gatekeeper's unsigned-app warning)."
echo "    To distribute to other Macs: scripts/package_dmg.sh, then"
echo "    scripts/notarize.sh (requires a paid Apple Developer account)."
