#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成 AppIcon.icns：深色圆角底 + 一条工具栏（几个圆角方块 + 一颗蓝色强调键）。

只用 AppKit + sips + iconutil，不依赖设计文件。
"""

import os
import subprocess

from AppKit import (
    NSBitmapImageFileTypePNG, NSBitmapImageRep, NSBezierPath, NSColor,
    NSDeviceRGBColorSpace, NSGraphicsContext, NSMakeRect, NSMakeSize,
)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SIZE = 1024


def draw(path):
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, SIZE, SIZE, 8, 4, True, False, NSDeviceRGBColorSpace, 0, 0)
    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)

    # 圆角深色底
    inset = SIZE * 0.08
    body = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(inset, inset, SIZE - 2 * inset, SIZE - 2 * inset),
        SIZE * 0.20, SIZE * 0.20)
    NSColor.colorWithCalibratedRed_green_blue_alpha_(0.11, 0.11, 0.13, 1.0).set()
    body.fill()

    # 一条工具栏
    bar_w = SIZE * 0.62
    bar_h = SIZE * 0.16
    bar_x = (SIZE - bar_w) / 2
    bar_y = (SIZE - bar_h) / 2
    strip = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(bar_x, bar_y, bar_w, bar_h), bar_h * 0.30, bar_h * 0.30)
    NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.10).set()
    strip.fill()

    # 键位方块
    n = 5
    pad = bar_h * 0.22
    cell = (bar_h - 2 * pad)
    step = (bar_w - 2 * pad - cell) / (n - 1)
    for i in range(n):
        r = NSMakeRect(bar_x + pad + i * step, bar_y + pad, cell, cell)
        b = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(r, cell * 0.28, cell * 0.28)
        if i == 1:
            NSColor.colorWithCalibratedRed_green_blue_alpha_(0.16, 0.52, 0.98, 1.0).set()
        else:
            NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.86).set()
        b.fill()

    NSGraphicsContext.restoreGraphicsState()
    data = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
    data.writeToFile_atomically_(path, True)


def main():
    iconset = os.path.join(ROOT, "build-pyi", "AppIcon.iconset")
    os.makedirs(iconset, exist_ok=True)
    master = os.path.join(ROOT, "build-pyi", "icon-1024.png")
    draw(master)
    for size in (16, 32, 64, 128, 256, 512):
        for scale in (1, 2):
            px = size * scale
            name = "icon_%dx%d%s.png" % (size, size, "@2x" if scale == 2 else "")
            subprocess.run(["sips", "-z", str(px), str(px), master, "--out",
                            os.path.join(iconset, name)], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["iconutil", "-c", "icns", iconset, "-o",
                    os.path.join(ROOT, "AppIcon.icns")], check=True)
    print("AppIcon.icns ok")


if __name__ == "__main__":
    main()
