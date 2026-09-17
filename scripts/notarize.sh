#!/usr/bin/env bash
# Signs "DominusBot.app", packages it into a DMG, signs the DMG, and
# submits it to Apple for notarization (spec section 49).
#
# Must run on macOS with:
#   - A paid Apple Developer Program enrollment.
#   - A "Developer ID Application" certificate already in the login
#     keychain (Xcode → Settings → Accounts → Manage Certificates → "+").
#   - An app-specific password generated at appleid.apple.com
#     (Sign-In and Security → App-Specific Passwords).
#
# Credentials come ONLY from environment variables — never hardcode them
# here or commit them anywhere:
#   APPLE_DEVELOPER_ID_APPLICATION   e.g. "Developer ID Application: Your Name (TEAMID)"
#   APPLE_ID                         the Apple ID email used for notarization
#   APPLE_TEAM_ID                    your Developer Team ID
#   APPLE_APP_SPECIFIC_PASSWORD      the app-specific password from appleid.apple.com
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUILD_DIR="$ROOT_DIR/build"
APP_NAME="DominusBot"
APP_BUNDLE="$BUILD_DIR/$APP_NAME.app"
DMG_PATH="$BUILD_DIR/DominusBot.dmg"

: "${APPLE_DEVELOPER_ID_APPLICATION:?set APPLE_DEVELOPER_ID_APPLICATION}"
: "${APPLE_ID:?set APPLE_ID}"
: "${APPLE_TEAM_ID:?set APPLE_TEAM_ID}"
: "${APPLE_APP_SPECIFIC_PASSWORD:?set APPLE_APP_SPECIFIC_PASSWORD}"

if [ ! -d "$APP_BUNDLE" ]; then
  echo "error: $APP_BUNDLE not found. Run scripts/build_mac.sh first." >&2
  exit 1
fi

echo "==> Signing $APP_BUNDLE"
codesign --deep --force --options runtime \
  --sign "$APPLE_DEVELOPER_ID_APPLICATION" \
  "$APP_BUNDLE"

echo "==> Verifying code signature"
codesign --verify --deep --strict --verbose=2 "$APP_BUNDLE"

echo "==> Packaging the signed app into a DMG"
"$ROOT_DIR/scripts/package_dmg.sh"

echo "==> Signing $DMG_PATH"
codesign --force --sign "$APPLE_DEVELOPER_ID_APPLICATION" "$DMG_PATH"

echo "==> Submitting for notarization (this can take a few minutes)"
xcrun notarytool submit "$DMG_PATH" \
  --apple-id "$APPLE_ID" \
  --team-id "$APPLE_TEAM_ID" \
  --password "$APPLE_APP_SPECIFIC_PASSWORD" \
  --wait

echo "==> Stapling the notarization ticket"
xcrun stapler staple "$DMG_PATH"

echo "==> Done: $DMG_PATH is signed, notarized, and stapled."
echo "    Any Mac can now open it without a Gatekeeper warning."
