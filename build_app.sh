#!/bin/bash
# 打包 TouchBar.app —— 菜单栏常驻（LSUIElement），无 Dock 图标。
set -euo pipefail
cd "$(dirname "$0")"

VENV=.venv
APP_NAME="TouchBar"
VER="0.1.2"
BUNDLE_ID="io.github.inyvn.touchbar"
OUT="dist-pyi"

if [ ! -x "$VENV/bin/python" ]; then
  echo "==> 创建构建环境 $VENV"
  UV=""
  for c in uv "$HOME/.local/bin/uv" /opt/homebrew/bin/uv /usr/local/bin/uv "$HOME/.hermes/bin/uv"; do
    if command -v "$c" >/dev/null 2>&1; then UV="$(command -v "$c")"; break; fi
  done
  [ -n "$UV" ] || { echo "!! 找不到 uv，无法创建构建环境" >&2; exit 1; }
  "$UV" venv --python 3.12 "$VENV"
  "$UV" pip install --python "$VENV/bin/python" -q \
    pyobjc-framework-Cocoa pyobjc-framework-ApplicationServices pyinstaller
fi
PY="$VENV/bin/python"

echo "==> 图标"
"$PY" tools/make_icon.py
[ -f AppIcon.icns ] || { echo "!! 图标没生成" >&2; exit 1; }

echo "==> 清理"
rm -rf build-pyi "$OUT"

echo "==> PyInstaller"
"$PY" -m PyInstaller \
  --noconfirm --clean --windowed \
  --name "$APP_NAME" \
  --osx-bundle-identifier "$BUNDLE_ID" \
  --icon "$PWD/AppIcon.icns" \
  --paths src \
  --distpath "$OUT" \
  --workpath build-pyi \
  --specpath build-pyi \
  --exclude-module tkinter \
  --exclude-module numpy \
  --exclude-module matplotlib \
  --hidden-import objc \
  --hidden-import AppKit \
  --hidden-import Quartz \
  --hidden-import ApplicationServices \
  src/touchbar.py

PLIST="$OUT/$APP_NAME.app/Contents/Info.plist"
echo "==> Info.plist"
/usr/libexec/PlistBuddy -c "Set :CFBundleShortVersionString $VER" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :CFBundleVersion string $VER" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $VER" "$PLIST"
/usr/libexec/PlistBuddy -c "Set :CFBundleName $APP_NAME" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :LSUIElement bool true" "$PLIST" 2>/dev/null \
  || /usr/libexec/PlistBuddy -c "Set :LSUIElement true" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 13.0" "$PLIST" 2>/dev/null || true

echo "==> 签名"
codesign --force --deep --sign - "$OUT/$APP_NAME.app"
codesign --verify --deep --strict "$OUT/$APP_NAME.app" && echo "    signature ok"

echo "==> 打包后自检"
"$OUT/$APP_NAME.app/Contents/MacOS/$APP_NAME" --selftest

echo "==> 完成: $OUT/$APP_NAME.app"
du -sh "$OUT/$APP_NAME.app"
