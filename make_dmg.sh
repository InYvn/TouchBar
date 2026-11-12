#!/bin/bash
# 打一个能直接发给用户的 DMG：TouchBar.app + 「应用程序」快捷方式 + 首次打开说明。
set -euo pipefail
cd "$(dirname "$0")"

APP="dist-pyi/TouchBar.app"
[ -d "$APP" ] || { echo "==> 没找到 $APP，先跑 ./build_app.sh" >&2; exit 1; }
VER=$(/usr/libexec/PlistBuddy -c "Print :CFBundleShortVersionString" "$APP/Contents/Info.plist")
OUT="dist-pyi/TouchBar-${VER}.dmg"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT

echo "==> 准备内容"
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/应用程序"
cat > "$STAGE/首次打开请看这里.txt" <<'TXT'
TouchBar 是菜单栏程序：打开后屏幕右上角出现一个工具栏图标，不会出现在 Dock 里。

首次打开若被系统拦下（adhoc 签名，不是文件坏了）：
  系统设置 → 隐私与安全性 → 安全性 → 「仍要打开」

必须授权：
  系统设置 → 隐私与安全性 → 辅助功能（macOS 27.3 叫「设备控制和数据访问」）
  在列表里把 TouchBar 打开，然后退出重开。

使用：
  - 工具条会自动跟随前台 App 的工具栏变化
  - 拖最左边的把手可以移动；靠近边缘松手会吸附成细标签，点标签展开
  - 半黑半白按钮切换不透明度；sidebar 按钮收纳到最近的边
  - 菜单栏图标里可以显示/隐藏、回到屏幕中央、退出
TXT

echo "==> 创建 DMG"
hdiutil create -volname "TouchBar" -srcfolder "$STAGE" -ov -format UDZO "$OUT" >/dev/null
echo "==> 完成: $OUT"
shasum -a 256 "$OUT"
du -sh "$OUT"
